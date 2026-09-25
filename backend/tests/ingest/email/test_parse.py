from datetime import UTC, datetime
from email.message import EmailMessage

from ingest.email.parse import (
    content_hash,
    html_to_text,
    normalize_whitespace,
    parse_message_id,
    parse_rfc822,
)


def test_message_id_strips_brackets_and_whitespace() -> None:
    assert parse_message_id("  <abc@example.com>  ") == "abc@example.com"
    assert parse_message_id("   ") is None
    assert parse_message_id(None) is None


def test_plain_body_is_preferred_over_html() -> None:
    raw = _message(
        message_id="<id@example.com>",
        plain="Hello   there",
        html="<p>Ignore</p>",
    )
    parsed = parse_rfc822(raw, provider_message_id="15", folder="INBOX")
    assert parsed.message_id == "id@example.com"
    assert parsed.body == "Hello there"
    assert parsed.provider_message_id == "15"
    assert parsed.subject == "Subject line"
    assert parsed.from_address == "from@example.com"
    assert parsed.to_addresses == ["to@example.com"]
    assert parsed.sent_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_html_only_body_strips_tags() -> None:
    raw = _message(message_id="<id@example.com>", plain=None, html="<p>Hello <b>there</b></p>")
    parsed = parse_rfc822(raw, provider_message_id="1", folder="INBOX")
    assert parsed.body == "Hello there"


def test_missing_message_id_is_none() -> None:
    raw = _message(message_id=None, plain="body", html=None)
    parsed = parse_rfc822(raw, provider_message_id="9", folder="INBOX")
    assert parsed.message_id is None


def test_content_hash_uses_normalized_body_and_subject() -> None:
    assert content_hash("Hello   there", "  Hi  ") == content_hash("Hello there", "Hi")
    assert content_hash("a", "b") != content_hash("a", "c")


def test_html_to_text_and_whitespace() -> None:
    assert html_to_text("<div>A</div><div>B</div>") == "A B"
    assert normalize_whitespace(" a \n b ") == "a b"


def _message(*, message_id: str | None, plain: str | None, html: str | None) -> bytes:
    message = EmailMessage()
    message["Subject"] = "Subject line"
    message["From"] = "Sender <from@example.com>"
    message["To"] = "to@example.com"
    message["Date"] = "Fri, 02 Jan 2026 03:04:05 +0000"
    if message_id is not None:
        message["Message-ID"] = message_id
    if plain is not None and html is not None:
        message.set_content(plain)
        message.add_alternative(html, subtype="html")
    elif html is not None:
        message.set_content(html, subtype="html")
    else:
        message.set_content(plain or "")
    return message.as_bytes()
