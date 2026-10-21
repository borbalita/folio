import httpx
import pytest

from app.config import settings
from ingest.notify import run


@pytest.fixture(autouse=True)
def token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "123:abc")


def test_chat_id_lists_the_chats_that_wrote_to_the_bot(capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bot123:abc/getUpdates"
        return httpx.Response(200, json={"ok": True, "result": [
            {"message": {"chat": {"id": 42, "first_name": "Borbala", "type": "private"}}},
            {"message": {"chat": {"id": 42, "first_name": "Borbala", "type": "private"}}},
        ]})

    code = run.main(["--chat-id"], client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert code == 0
    assert capsys.readouterr().out.strip() == "42  Borbala (private)"


def test_chat_id_with_no_messages_says_what_to_do(capsys) -> None:
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"ok": True, "result": []})
    ))

    assert run.main(["--chat-id"], client=client) == 1
    assert "Send your bot a message" in capsys.readouterr().err


def test_missing_token_is_reported(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", None)

    assert run.main(["--chat-id"]) == 1
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_test_message_goes_to_the_configured_chat(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bot123:abc/sendMessage"
        sent.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"ok": True})

    code = run.main(["--test"], client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert code == 0
    assert sent == [{"chat_id": "42", "text": "✅ Folio notifications are set up."}]
