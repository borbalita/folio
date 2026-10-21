from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from app.config import settings
from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.email.message import EmailMessage
from app.database.models.finance.invoice import Invoice
from app.database.models.user import User
from app.demo import live
from app.demo.emails import draw_invoice
from ingest.email.invoices import ExtractedInvoice

USER = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
NOW = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
SEED = 7


class _MemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.closed = False

    def get(self, model: type, ident: uuid.UUID) -> User | None:
        return User(id=ident, email="demo@example.com") if model is User else None

    def scalar(self, _statement: object) -> None:
        return None

    def scalars(self, _statement: object) -> list[object]:
        return []

    def add(self, row: object) -> None:
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()  # type: ignore[attr-defined]
        self.added.append(row)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def delete(self, _row: object) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _send(
    monkeypatch: pytest.MonkeyPatch, kind: str, extract
) -> tuple[_MemorySession, dict, list]:
    session = _MemorySession()
    matched: list[uuid.UUID] = []
    seen_tags: list[list[str]] = []

    class _Tags:
        def __init__(self, *, tags: list[str]) -> None:
            seen_tags.append(tags)

        def __enter__(self) -> None:
            return None

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(live, "propagate_attributes", _Tags)
    monkeypatch.setattr(live, "_stored_invoices", lambda _mailbox_id, _message_id: [])
    result = live.send_invoice(
        USER,
        kind,  # type: ignore[arg-type]
        rng=random.Random(SEED),
        now=NOW,
        open_session=lambda: session,
        match=lambda user_id: matched.append(user_id) or {"linked": 0, "suggested": 0},
        embed=lambda texts: [
            [0.0] * settings.openai_embedding_dimensions for _ in texts
        ],
        classifier=lambda _prompt: "invoice",
        invoice_check=lambda _source: "to_pay",
        invoice_extract=extract,
    )
    assert seen_tags == [["demo"]]
    assert matched == [USER]
    assert session.closed
    return session, result, seen_tags


def _expected():
    return draw_invoice(random.Random(SEED), "normal", NOW.date())


def test_a_normal_invoice_is_stored_open_for_the_demo_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _expected()

    def extract(_source):
        return [
            ExtractedInvoice(
                payee=built.vendor.name,
                iban=built.iban,
                amount=float(built.amount),
                currency="EUR",
                invoice_number=built.number,
            )
        ]

    session, result, _tags = _send(monkeypatch, "normal", extract)

    [mailbox] = [row for row in session.added if isinstance(row, Mailbox)]
    [email] = [row for row in session.added if isinstance(row, EmailMessage)]
    [invoice] = [row for row in session.added if isinstance(row, Invoice)]
    assert mailbox.provider == MailboxProvider.DEMO
    assert mailbox.user_id == USER
    assert email.mailbox_id == mailbox.id
    assert email.message_id.startswith("<demo-")
    assert invoice.status == "open"
    assert invoice.payee == built.vendor.name
    assert invoice.iban == built.iban
    assert invoice.amount == built.amount.quantize(Decimal("0.01"))
    assert result["sent"] == {
        "kind": "normal",
        "vendor": built.vendor.name,
        "number": built.number,
        "amount": str(built.amount),
    }
    assert result["failures"] == 0
    assert result["error"] is None


def test_a_model_error_is_reported_and_stored_as_today(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(_source):
        raise UnexpectedModelBehavior("bad output")

    session, result, _tags = _send(monkeypatch, "normal", failing)

    [invoice] = [row for row in session.added if isinstance(row, Invoice)]
    assert invoice.status == "needs_info"
    assert invoice.issues == ["extraction_failed"]
    assert result["failures"] == 1
    assert "could not" in result["error"]


def test_random_picks_one_of_the_three_kinds() -> None:
    kinds = {live.resolve_kind("random", random.Random(seed)) for seed in range(40)}

    assert kinds == {"normal", "already_paid", "online_only"}
    assert live.resolve_kind("online_only", random.Random(1)) == "online_only"
