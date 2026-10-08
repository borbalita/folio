from datetime import UTC, datetime
from email.message import EmailMessage

import pytest

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
    assert parsed.from_name == "Sender"
    assert parsed.to_addresses == ["to@example.com"]
    assert parsed.sent_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_sender_without_a_display_name_has_an_empty_name() -> None:
    message = EmailMessage()
    message["From"] = "from@example.com"
    message.set_content("Hello")
    parsed = parse_rfc822(bytes(message), provider_message_id="2", folder="INBOX")
    assert (parsed.from_name, parsed.from_address) == ("", "from@example.com")


def test_html_only_body_strips_tags() -> None:
    raw = _message(
        message_id="<id@example.com>", plain=None, html="<p>Hello <b>there</b></p>"
    )
    parsed = parse_rfc822(raw, provider_message_id="1", folder="INBOX")
    assert parsed.body == "Hello there"


def test_missing_message_id_is_none() -> None:
    raw = _message(message_id=None, plain="body", html=None)
    parsed = parse_rfc822(raw, provider_message_id="9", folder="INBOX")
    assert parsed.message_id is None


def test_content_hash_uses_normalized_body_and_subject() -> None:
    assert content_hash("Hello   there", "  Hi  ") == content_hash("Hello there", "Hi")
    assert content_hash("a", "b") != content_hash("a", "c")


@pytest.mark.parametrize(
    ("payload", "maintype", "subtype", "filename", "kept"),
    [
        (b"%PDF-small", "application", "pdf", "invoice.pdf", True),
        (b"not-a-pdf", "application", "octet-stream", "scan.PDF", True),
        (b"png", "image", "png", "logo.png", False),
    ],
)
def test_only_pdf_bytes_are_kept(
    payload: bytes, maintype: str, subtype: str, filename: str, kept: bool
) -> None:
    message = EmailMessage()
    message["Subject"] = "Invoice"
    message["From"] = "billing@example.com"
    message["To"] = "you@yahoo.com"
    message["Date"] = "Fri, 02 Jan 2026 03:04:05 +0000"
    message["Message-ID"] = "<id@example.com>"
    message.set_content("See attached.")
    message.add_attachment(
        payload, maintype=maintype, subtype=subtype, filename=filename
    )
    parsed = parse_rfc822(message.as_bytes(), provider_message_id="1", folder="INBOX")
    assert parsed.attachment_filenames == (filename,)
    if kept:
        assert [(item.filename, item.content) for item in parsed.attachments] == [
            (filename, payload)
        ]
    else:
        assert parsed.attachments == ()


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


_ENCODED_RAW = b"""\
Subject: =?UTF-8?Q?=C3=89rtes=C3=ADt=C3=A9s?= =?utf-8?Q?_sz=C3=A1mla?=
From: billing@example.com
To: you@yahoo.com
Date: Fri, 02 Jan 2026 03:04:05 +0000
Message-ID: <encoded@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="b"

--b
Content-Type: text/plain; charset=utf-8

See attached.
--b
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="=?utf-8?Q?Neue_Rechnung_M=C3=A4rz.pdf?="
Content-Transfer-Encoding: base64

JVBERi0xLjQ=
--b--
"""


def test_encoded_subject_and_filename_are_decoded() -> None:
    parsed = parse_rfc822(_ENCODED_RAW, provider_message_id="1", folder="INBOX")

    assert parsed.subject == "Értesítés számla"
    assert parsed.attachment_filenames == ("Neue Rechnung März.pdf",)
    # Only recognizable as a PDF once the filename is decoded.
    assert [(item.filename, item.content) for item in parsed.attachments] == [
        ("Neue Rechnung März.pdf", b"%PDF-1.4")
    ]


def test_unknown_charset_keeps_the_raw_header() -> None:
    raw = _ENCODED_RAW.replace(b"=?UTF-8?Q?=C3=89rtes", b"=?x-bogus?Q?=C3=89rtes")

    parsed = parse_rfc822(raw, provider_message_id="1", folder="INBOX")

    assert parsed.subject.startswith("=?x-bogus?Q?")
