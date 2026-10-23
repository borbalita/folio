"""The demo user's everyday mail as finished rows: emails and their search chunks.

Appointment placeholders are filled for the reset day, so "this month" stays true whenever the
demo is reset. No model is called: labels and embeddings come from the fixture.
"""

from __future__ import annotations

import re
import uuid
import zlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import settings
from app.database.models.email.chunk import EmailChunk
from app.database.models.email.message import EmailMessage
from app.demo.accounts import DemoAccounts
from app.demo.embed_mail_fixture import chunk_text
from app.demo.mail_dates import AppointmentRule, appointment_dates, render
from app.demo.mail_fixture import FixtureMail, load_fixture
from ingest.email.parse import content_hash

_PLACEHOLDER = re.compile(r"\{([a-z_]+)(?::short)?\}")


@dataclass(frozen=True, slots=True)
class MailRows:
    emails: list[EmailMessage]
    chunks: list[EmailChunk]


def _sent_at(mail: FixtureMail, today: date, dates: dict[str, datetime]) -> datetime:
    """today − days_ago during office hours, but before every appointment the mail mentions."""
    zone = ZoneInfo(settings.email_timezone)
    # A stable hour per email, so the inbox doesn't show 40 mails at the same minute.
    spread = zlib.crc32(mail.key.encode())
    sent = datetime.combine(
        today - timedelta(days=mail.days_ago),
        time(8 + spread % 10, spread % 60),
        tzinfo=zone,
    )
    mentioned = [dates[name] for name in _PLACEHOLDER.findall(mail.subject + mail.body)]
    if mentioned:
        sent = min(sent, min(mentioned) - timedelta(days=1))
    return sent


def build_mail_rows(
    today: date,
    accounts: DemoAccounts,
    *,
    to_address: str,
    fixture: tuple[dict[str, AppointmentRule], list[FixtureMail]] | None = None,
) -> MailRows:
    rules, mails = fixture or load_fixture()
    dates = appointment_dates(rules, today)
    emails: list[EmailMessage] = []
    chunks: list[EmailChunk] = []
    for mail in mails:
        subject, body = render(mail.subject, dates), render(mail.body, dates)
        message_id = f"<demo-mail-{uuid.uuid4()}@folio.example>"
        email = EmailMessage(
            id=uuid.uuid4(),
            mailbox_id=accounts.mailbox_id,
            message_id=message_id,
            provider_message_id=message_id,
            folder="INBOX",
            subject=subject,
            from_address=mail.from_address,
            from_name=mail.from_name,
            to_addresses=[to_address],
            sent_at=_sent_at(mail, today, dates),
            body=body,
            label=mail.label,
            newsletter_source=None,
            content_hash=content_hash(body, subject),
            embedding_model=settings.openai_embedding_model,
            embedding_dimensions=settings.openai_embedding_dimensions,
        )
        emails.append(email)
        chunks.append(
            EmailChunk(
                id=uuid.uuid4(),
                email_id=email.id,
                chunk_index=0,
                chunk_text=chunk_text(subject, body),
                token_count=mail.token_count,
                embedding=mail.embedding,
            )
        )
    return MailRows(emails, chunks)
