"""Turn a raw RFC822 message into the fields the email pipeline stores."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ParsedAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    message_id: str | None
    provider_message_id: str
    folder: str
    subject: str
    from_address: str
    from_name: str
    """Display name from the From header; empty when there is none."""
    to_addresses: list[str]
    sent_at: datetime
    body: str
    attachment_filenames: tuple[str, ...] = ()
    attachments: tuple[ParsedAttachment, ...] = ()


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def decode_header_text(value: str) -> str:
    """Decode RFC 2047 encoded words (`=?UTF-8?Q?...?=`); the compat32 parser leaves them raw."""
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeDecodeError, ValueError):
        # Unknown charset or a malformed encoded word: keep the raw header.
        return value


def parse_message_id(header: str | None) -> str | None:
    if header is None:
        return None
    cleaned = header.strip().removeprefix("<").removesuffix(">").strip()
    return cleaned or None


def content_hash(body: str, subject: str) -> str:
    payload = f"{normalize_whitespace(body)}\n{normalize_whitespace(subject)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return normalize_whitespace(" ".join(parser.parts))


def parse_rfc822(raw: bytes, *, provider_message_id: str, folder: str) -> ParsedMessage:
    message = message_from_bytes(raw)
    subject = normalize_whitespace(decode_header_text(message.get("Subject", "")))
    from_values = getaddresses(message.get_all("From", []))
    from_name, from_address = from_values[0] if from_values else ("", "")
    to_addresses = [addr for _, addr in getaddresses(message.get_all("To", [])) if addr]
    sent_at = _sent_at(message)
    return ParsedMessage(
        message_id=parse_message_id(message.get("Message-ID")),
        provider_message_id=provider_message_id,
        folder=folder,
        subject=subject,
        from_address=from_address,
        from_name=normalize_whitespace(decode_header_text(from_name)),
        to_addresses=to_addresses,
        sent_at=sent_at,
        body=_body(message),
        attachment_filenames=_attachment_filenames(message),
        attachments=_pdf_attachments(message),
    )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


def _body(message: Message) -> str:
    plain = _part_text(message, "text/plain")
    if plain is not None:
        return normalize_whitespace(plain)
    html = _part_text(message, "text/html")
    if html is not None:
        return html_to_text(html)
    return ""


def _part_text(message: Message, content_type: str) -> str | None:
    if message.get_content_type() == content_type and not message.is_multipart():
        return _decode(message)
    if not message.is_multipart():
        return None
    for part in message.walk():
        if (
            part.get_content_type() == content_type
            and part.get_content_disposition() != "attachment"
        ):
            text = _decode(part)
            if text is not None:
                return text
    return None


def _decode(part: Message) -> str | None:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return None
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _attachment_filenames(message: Message) -> tuple[str, ...]:
    names: list[str] = []
    for part in message.walk():
        filename = part.get_filename()
        if filename:
            names.append(decode_header_text(filename))
    return tuple(names)


def _pdf_attachments(message: Message) -> tuple[ParsedAttachment, ...]:
    found: list[ParsedAttachment] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        raw_filename = part.get_filename()
        filename = decode_header_text(raw_filename) if raw_filename else None
        content_type = part.get_content_type()
        if not _is_pdf(filename, content_type):
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        found.append(
            ParsedAttachment(
                filename=filename or "attachment.pdf",
                content_type=content_type,
                content=payload,
            )
        )
    return tuple(found)


def _is_pdf(filename: str | None, content_type: str) -> bool:
    if content_type == "application/pdf":
        return True
    return bool(filename and filename.lower().endswith(".pdf"))


def _sent_at(message: Message) -> datetime:
    header = message.get("Date")
    if not header:
        return datetime.now(UTC)
    parsed = parsedate_to_datetime(header)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
