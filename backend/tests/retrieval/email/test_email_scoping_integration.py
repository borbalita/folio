"""Email search scoping against the real eval database (see evals/README.md).

Run: uv run --env-file .env.eval pytest -m integration tests/retrieval/email
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.database.engine import get_engine
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailRetriever
from evals.fixtures import A_ACTIVE, A_INACTIVE, B_ACTIVE, MAILBOXES, USER_A
from evals.guard import require_local_database
from ingest.email.parse import ParsedMessage
from ingest.email.pipeline import ingest_messages

pytestmark = pytest.mark.integration

# Every chunk and the query share one vector, so semantic search matches all mail
# and only the SQL scope can exclude any of it.
VECTOR = [1.0] + [0.0] * (settings.openai_embedding_dimensions - 1)
KEYWORD = "scopingprobe"


def _message(mailbox_key: str) -> ParsedMessage:
    return ParsedMessage(
        message_id=f"scoping-{mailbox_key}@example.com",
        provider_message_id=f"scoping-{mailbox_key}",
        folder="INBOX",
        subject=f"Invoice {KEYWORD} {mailbox_key}",
        from_address="billing@example.com",
        to_addresses=["someone@example.com"],
        sent_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        body=f"Your {KEYWORD} invoice for September is attached.",
    )


@pytest.fixture
def session() -> Iterator[Session]:
    """A session whose commits stay inside one outer transaction, rolled back at the end."""
    require_local_database(settings.database_url)
    with get_engine().connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def test_search_returns_only_the_users_active_mailbox(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.retrieval.base.embed_query", lambda _query: VECTOR)
    monkeypatch.setattr(
        "app.retrieval.base.extract_fts_keywords",
        lambda _query, *, system_prompt: KEYWORD,
    )
    for mailbox in MAILBOXES:
        ingest_messages(
            session,
            mailbox.id,
            [_message(mailbox.address)],
            embed=lambda texts: [VECTOR for _ in texts],
            classifier=lambda _prompt: "invoice",
        )

    filters = EmailSearchFilters(
        user_id=USER_A,
        # The inactive mailbox and another user's mailbox are passed on purpose:
        # the SQL must exclude them even if a caller lists them.
        mailbox_ids=[A_ACTIVE.id, A_INACTIVE.id, B_ACTIVE.id],
    )
    found = EmailRetriever().search(KEYWORD, filters=filters, session=session)

    # The probe chunks match the query exactly, so any that leaked through would rank first.
    # Other mail already in the eval mailbox may fill the rest of the results.
    assert {passage.mailbox_name for passage in found} == {A_ACTIVE.display_name}
    probes = {passage.subject for passage in found if KEYWORD in passage.subject}
    assert probes == {f"Invoice {KEYWORD} {A_ACTIVE.address}"}
