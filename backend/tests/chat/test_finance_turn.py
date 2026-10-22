from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
import structlog

from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import run_turn
from app.database import chats, invoices, mailboxes, payments
from app.finance_assistant import tools
from app.finance_assistant.outputs import FinanceAnswer, FinanceCard
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID

USER = CurrentUser(id=TEST_USER_ID, email="test@example.com")
OPEN_A = uuid.uuid4()
OPEN_B = uuid.uuid4()
DRAFT_A = uuid.uuid4()
DRAFT_B = uuid.uuid4()


class _Usage:
    requests = 1
    input_tokens = 2
    output_tokens = 3
    tool_calls = 1


class _Agent:
    """Stands in for the model: runs real tools, then answers with the given cards."""

    def __init__(self, steps, answer: FinanceAnswer) -> None:
        self.steps = steps
        self.answer = answer

    async def run(self, prompt: str, deps: object) -> SimpleNamespace:
        for step in self.steps:
            step(deps)
        return SimpleNamespace(output=self.answer, usage=_Usage())


def _invoice(id_: uuid.UUID) -> dict:
    return {"id": str(id_), "payee": "Stadtwerke", "amount": "50.00", "currency": "EUR",
            "dueDate": "2026-10-20", "status": "open", "reference": "R"}


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    rows: list[dict] = []
    monkeypatch.setattr(
        mailboxes, "invoice_mailbox_ids", lambda user_id: [uuid.uuid4()]
    )
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)

    def append(thread_id, messages):
        rows.extend(messages)
        return [{"id": str(uuid.uuid4())} for _ in messages]

    monkeypatch.setattr(chats, "append_messages", append)
    monkeypatch.setattr(invoices, "list_invoices", lambda mailbox_ids: [_invoice(OPEN_A), _invoice(OPEN_B)])
    return rows


def _use(monkeypatch: pytest.MonkeyPatch, agent: _Agent) -> None:
    monkeypatch.setattr("app.finance_assistant.agent.get_agent", lambda: agent)


def _run(text: str) -> str:
    async def collect() -> list[str]:
        return [
            frame
            async for frame in run_turn(
                USER,
                TEST_THREAD_ID,
                [{"role": "user", "content": text}],
                thread={"id": str(TEST_THREAD_ID), "title": "Thread", "agent": "finance"},
            )
        ]

    return "".join(asyncio.run(collect()))


def _cards(frames: str) -> list[dict]:
    return [
        json.loads(line[len("data: "):])["data"]
        for line in frames.splitlines()
        if line.startswith("data: {") and '"data-finance-card"' in line
    ]


def _stored_cards(rows: list[dict]) -> list[dict]:
    assistant = rows[-1]["message"]
    return [part["data"] for part in assistant["parts"] if part["type"] == "data-finance-card"]


def test_open_invoices_answer_shows_an_invoice_card(monkeypatch, stored) -> None:
    _use(monkeypatch, _Agent(
        [lambda deps: tools.execute_list_invoices(deps, "open")],
        FinanceAnswer(answer="Two invoices are open.",
                      cards=[FinanceCard(kind="invoices", ids=[OPEN_A, OPEN_B])]),
    ))

    frames = _run("What do I still need to pay?")

    expected = {"kind": "invoices", "ids": [str(OPEN_A), str(OPEN_B)]}
    assert _cards(frames) == [expected]
    assert _stored_cards(stored) == [expected]
    assert "Two invoices are open." in frames


def test_pay_them_all_creates_drafts_and_payment_cards_none_approved(monkeypatch, stored) -> None:
    created: list[list[uuid.UUID]] = []

    def create_drafts(invoice_ids, mailbox_ids):
        created.append(invoice_ids)
        return {"drafts": [{"id": str(DRAFT_A), "invoiceId": str(OPEN_A), "amount": "50.00", "currency": "EUR"},
                           {"id": str(DRAFT_B), "invoiceId": str(OPEN_B), "amount": "50.00", "currency": "EUR"}],
                "skipped": []}

    def approve(*_args, **_kwargs):
        raise AssertionError("chat must never approve")

    monkeypatch.setattr(payments, "create_drafts", create_drafts)
    monkeypatch.setattr(payments, "approve", approve)
    _use(monkeypatch, _Agent(
        [lambda deps: tools.execute_list_invoices(deps, "open"),
         lambda deps: tools.execute_prepare_payments(deps, [OPEN_A, OPEN_B])],
        FinanceAnswer(answer="Prepared two payments; they await your approval.",
                      cards=[FinanceCard(kind="payments", ids=[DRAFT_A, DRAFT_B])]),
    ))

    frames = _run("Pay them all")

    assert created == [[OPEN_A, OPEN_B]]
    assert _stored_cards(stored) == [{"kind": "payments", "ids": [str(DRAFT_A), str(DRAFT_B)]}]
    assert _cards(frames) == _stored_cards(stored)


def test_unknown_card_id_is_dropped_and_logged(monkeypatch, stored) -> None:
    invented = uuid.uuid4()
    _use(monkeypatch, _Agent(
        [lambda deps: tools.execute_list_invoices(deps, "open")],
        FinanceAnswer(answer="Here they are.", cards=[
            FinanceCard(kind="invoices", ids=[OPEN_A, invented]),
            FinanceCard(kind="payments", ids=[uuid.uuid4()]),
        ]),
    ))

    with structlog.testing.capture_logs() as logs:
        frames = _run("What's open?")

    assert _cards(frames) == [{"kind": "invoices", "ids": [str(OPEN_A)]}]
    dropped = [entry for entry in logs if entry["event"] == "finance_card_id_dropped"]
    assert {(entry["kind"], entry["count"]) for entry in dropped} == {("invoices", 1), ("payments", 1)}
    assert all(str(invented) not in json.dumps(entry, default=str) for entry in dropped)


def test_finance_turn_uses_the_invoice_scope(monkeypatch, stored) -> None:
    invoice_scope = [uuid.uuid4()]
    seen: list[list[uuid.UUID]] = []
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [])
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [])
    monkeypatch.setattr(
        mailboxes, "invoice_mailbox_ids", lambda user_id: invoice_scope
    )
    _use(
        monkeypatch,
        _Agent(
            [lambda deps: seen.append(deps.mailbox_ids)],
            FinanceAnswer(answer="Nothing to pay.", cards=[]),
        ),
    )

    _run("What do I owe?")

    assert seen == [invoice_scope]
