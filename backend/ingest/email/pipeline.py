"""Store parsed mail, skip messages that are already embedded, chunk the rest."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
import tiktoken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.engine import get_session_factory
from app.database.models.email.chunk import EmailChunk
from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.email.message import EmailLabel, EmailMessage
from app.database.models.user import User
from ingest.email.parse import ParsedMessage, content_hash
from ingest.tokens import CHUNK_MAX_TOKENS, EMBEDDING_MAX_TOKENS
from ingest.embeddings import embed_texts

log = structlog.get_logger(__name__)

STUB_LABEL = EmailLabel.FYI


@dataclass
class IngestSummary:
    fetched: int = 0
    skipped: int = 0
    new: int = 0
    reembedded: int = 0
    missing_message_id: int = 0
    labels: dict[str, int] = field(default_factory=dict)
    attachments_saved: int = 0
    attachments_skipped: int = 0
    news_items: int = 0
    stories_rebuilt: int = 0

    def render(self) -> str:
        label_counts = ", ".join(
            f"{name}={count}" for name, count in sorted(self.labels.items())
        )
        return "\n".join(
            [
                f"fetched: {self.fetched}",
                f"skipped: {self.skipped}",
                f"new: {self.new}",
                f"re-embedded: {self.reembedded}",
                f"labels: {label_counts or 'none'}",
                f"attachments saved: {self.attachments_saved}",
                f"attachments skipped: {self.attachments_skipped}",
                f"news items: {self.news_items}",
                f"stories rebuilt: {self.stories_rebuilt}",
            ]
        )


@dataclass(frozen=True, slots=True)
class StoredEmail:
    content_hash: str
    embedding_model: str
    embedding_dimensions: int


def chunk_email_text(text: str) -> list[tuple[str, int]]:
    normalized = text.strip()
    if not normalized:
        return [("", 1)]
    encoding = tiktoken.encoding_for_model(settings.openai_embedding_model)
    tokens = encoding.encode(normalized, disallowed_special=())
    pieces = [
        tokens[start : start + CHUNK_MAX_TOKENS]
        for start in range(0, len(tokens), CHUNK_MAX_TOKENS)
    ]
    return [(encoding.decode(piece), len(piece)) for piece in pieces] or [("", 1)]


def ingest_action(stored: StoredEmail | None, parsed: ParsedMessage) -> str:
    """Return skip, new, or reembed. Skip only when mailbox, id, hash, model, and dims match."""
    if stored is None:
        return "new"
    same = (
        stored.content_hash == content_hash(parsed.body, parsed.subject)
        and stored.embedding_model == settings.openai_embedding_model
        and stored.embedding_dimensions == settings.openai_embedding_dimensions
    )
    return "skip" if same else "reembed"


def ingest_messages(
    session: Session,
    mailbox_id: uuid.UUID,
    messages: list[ParsedMessage],
    *,
    embed=embed_texts,
) -> IngestSummary:
    summary = IngestSummary(fetched=len(messages))
    for parsed in messages:
        if not parsed.message_id:
            summary.missing_message_id += 1
            log.warning(
                "email_missing_message_id",
                provider_message_id=parsed.provider_message_id,
                subject=parsed.subject,
            )
            continue
        action = _store_one(session, mailbox_id, parsed, embed)
        session.commit()
        if action == "skip":
            summary.skipped += 1
        elif action == "new":
            summary.new += 1
            summary.labels[STUB_LABEL] = summary.labels.get(STUB_LABEL, 0) + 1
        else:
            summary.reembedded += 1
            summary.labels[STUB_LABEL] = summary.labels.get(STUB_LABEL, 0) + 1
    return summary


def _store_one(session: Session, mailbox_id: uuid.UUID, parsed: ParsedMessage, embed) -> str:
    stored_row = session.scalar(
        select(EmailMessage).where(
            EmailMessage.mailbox_id == mailbox_id,
            EmailMessage.message_id == parsed.message_id,
        )
    )
    stored = None
    if stored_row is not None:
        stored = StoredEmail(
            content_hash=stored_row.content_hash,
            embedding_model=stored_row.embedding_model,
            embedding_dimensions=stored_row.embedding_dimensions,
        )
    action = ingest_action(stored, parsed)
    if action == "skip":
        return action

    digest = content_hash(parsed.body, parsed.subject)
    pieces = chunk_email_text(f"{parsed.subject}\n{parsed.body}")
    for text, token_count in pieces:
        if token_count > EMBEDDING_MAX_TOKENS:
            raise ValueError(
                f"Email chunk has {token_count} tokens, over the {EMBEDDING_MAX_TOKENS} limit"
            )
    vectors = embed([text for text, _count in pieces])
    if stored_row is None:
        stored_row = EmailMessage(
            mailbox_id=mailbox_id,
            message_id=parsed.message_id,
            provider_message_id=parsed.provider_message_id,
            folder=parsed.folder,
            subject=parsed.subject,
            from_address=parsed.from_address,
            to_addresses=parsed.to_addresses,
            sent_at=parsed.sent_at,
            body=parsed.body,
            label=STUB_LABEL,
            content_hash=digest,
            embedding_model=settings.openai_embedding_model,
            embedding_dimensions=settings.openai_embedding_dimensions,
        )
        session.add(stored_row)
        session.flush()
    else:
        stored_row.provider_message_id = parsed.provider_message_id
        stored_row.folder = parsed.folder
        stored_row.subject = parsed.subject
        stored_row.from_address = parsed.from_address
        stored_row.to_addresses = parsed.to_addresses
        stored_row.sent_at = parsed.sent_at
        stored_row.body = parsed.body
        stored_row.label = STUB_LABEL
        stored_row.content_hash = digest
        stored_row.embedding_model = settings.openai_embedding_model
        stored_row.embedding_dimensions = settings.openai_embedding_dimensions
        stored_row.updated_at = datetime.now(UTC)
        for chunk in list(stored_row_chunks(session, stored_row.id)):
            session.delete(chunk)
        session.flush()
    for index, ((text, token_count), vector) in enumerate(
        zip(pieces, vectors, strict=True)
    ):
        session.add(
            EmailChunk(
                email_id=stored_row.id,
                chunk_index=index,
                chunk_text=text,
                token_count=token_count,
                embedding=vector,
            )
        )
    return action


def stored_row_chunks(session: Session, email_id: uuid.UUID) -> list[EmailChunk]:
    return list(
        session.scalars(select(EmailChunk).where(EmailChunk.email_id == email_id))
    )


def upsert_yahoo_mailbox(session: Session) -> Mailbox:
    owner_id = settings.email_agent_owner_user_id
    address = settings.yahoo_email
    if owner_id is None or address is None:
        raise RuntimeError("Yahoo settings are missing")
    owner = session.get(User, owner_id)
    if owner is None:
        raise RuntimeError(f"No users row for {owner_id}")
    mailbox = session.scalar(
        select(Mailbox).where(
            Mailbox.provider == MailboxProvider.YAHOO, Mailbox.address == address
        )
    )
    if mailbox is None:
        mailbox = Mailbox(
            user_id=owner_id,
            provider=MailboxProvider.YAHOO,
            address=address,
            display_name=address,
        )
        session.add(mailbox)
        session.flush()
    return mailbox


def record_sync(
    session: Session, mailbox: Mailbox, *, uidvalidity: int, highest_uid: int | None
) -> None:
    mailbox.last_synced_at = datetime.now(UTC)
    mailbox.sync_cursor = {"uidvalidity": uidvalidity, "highest_uid": highest_uid}
    session.commit()


def ingest_fetched(
    session: Session,
    messages: list[ParsedMessage],
    *,
    uidvalidity: int,
    highest_uid: int | None,
    embed=embed_texts,
) -> IngestSummary:
    mailbox = upsert_yahoo_mailbox(session)
    session.commit()
    summary = ingest_messages(session, mailbox.id, messages, embed=embed)
    record_sync(
        session, mailbox, uidvalidity=uidvalidity, highest_uid=highest_uid
    )
    return summary


def open_session() -> Session:
    return get_session_factory()()
