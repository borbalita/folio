from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
import structlog

from app.config import settings
from app.database.models.notification import Notification
from app.notifications import telegram

# 12:00 in Berlin (CEST, UTC+2).
NOON = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "123:abc")
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    monkeypatch.setattr(settings, "app_url", "https://folio.test")
    monkeypatch.setattr(telegram, "PAUSE_SECONDS", 0)


def rows(*texts: str) -> list[Notification]:
    return [
        Notification(key=f"k{i}", kind="invoice_new", status="pending", text=text, attempts=0)
        for i, text in enumerate(texts)
    ]


def session_with(pending: list[Notification]) -> MagicMock:
    session = MagicMock()
    session.scalars.return_value = pending
    return session


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pending_rows_are_sent_oldest_first() -> None:
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bot123:abc/sendMessage"
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    pending = rows("first", "second")
    session = session_with(pending)

    counts = telegram.send_pending(session, NOON, client=client(handler))

    assert [m["text"] for m in sent] == ["first", "second"]
    assert all(m["chat_id"] == "42" for m in sent)
    assert [r.status for r in pending] == ["sent", "sent"]
    assert all(r.sent_at == NOON for r in pending)
    assert counts == {"sent": 2, "failed": 0, "held": 0}
    assert session.commit.call_count == 2


@pytest.mark.parametrize(
    ("berlin_hour", "berlin_minute", "sends"),
    [(21, 59, True), (22, 0, False), (6, 59, False), (7, 0, True)],
)
def test_quiet_hours(berlin_hour: int, berlin_minute: int, sends: bool) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"ok": True})

    # Berlin is UTC+2 on 19 Oct 2026.
    now = datetime(2026, 10, 19, berlin_hour, berlin_minute, tzinfo=UTC) - timedelta(hours=2)
    pending = rows("x")

    counts = telegram.send_pending(session_with(pending), now, client=client(handler))

    assert bool(calls) is sends
    assert pending[0].status == ("sent" if sends else "pending")
    assert counts["held"] == (0 if sends else 1)


@pytest.mark.parametrize("status", [429, 502])
def test_retryable_answer_keeps_the_row_pending_until_five_attempts(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"ok": False})

    [row] = pending = rows("x")
    for attempt in range(1, 6):
        telegram.send_pending(session_with(pending), NOON, client=client(handler))
        assert row.attempts == attempt
        assert row.last_error == str(status)
        assert row.status == ("pending" if attempt < 5 else "failed")


def test_network_error_counts_an_attempt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    [row] = pending = rows("x")
    counts = telegram.send_pending(session_with(pending), NOON, client=client(handler))

    assert (row.status, row.attempts, row.last_error) == ("pending", 1, "ConnectError")
    assert counts["failed"] == 0


def test_bad_token_fails_the_row_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    pending = rows("secret invoice text", "second")
    with structlog.testing.capture_logs() as logs:
        counts = telegram.send_pending(session_with(pending), NOON, client=client(handler))

    assert calls == [1]
    assert [r.status for r in pending] == ["failed", "pending"]
    assert counts == {"sent": 0, "failed": 1, "held": 0}
    [entry] = [e for e in logs if e["event"] == "telegram_misconfigured"]
    assert entry["status"] == 401
    assert "secret invoice text" not in json.dumps(logs)


def test_off_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_chat_id", None)
    session = session_with(rows("x"))

    counts = telegram.send_pending(session, NOON, client=client(lambda r: httpx.Response(200)))

    assert counts == {"sent": 0, "failed": 0, "held": 0}
    session.scalars.assert_not_called()


def test_the_token_never_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG", logger="httpx")

    telegram.send_pending(
        session_with(rows("x")), NOON, client=client(lambda r: httpx.Response(200, json={"ok": True}))
    )

    assert any("sendMessage" in record.getMessage() for record in caplog.records)
    assert not any("123:abc" in record.getMessage() for record in caplog.records)
