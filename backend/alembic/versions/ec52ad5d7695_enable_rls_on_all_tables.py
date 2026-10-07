"""enable rls on all tables

Revision ID: ec52ad5d7695
Revises: 6459ddacd6e8
Create Date: 2026-10-02 14:39:39.220763

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ec52ad5d7695'
down_revision: str | Sequence[str] | None = '6459ddacd6e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# RLS with no policies: the anon and authenticated roles (whose key ships in the
# frontend) read nothing over the Data API; the backend's service role bypasses RLS.
RLS_TABLES = (
    "alembic_version",
    "users",
    "source_documents",
    "document_chunks",
    "chat_threads",
    "chat_messages",
    "message_citations",
    "email_citations",
    "mailboxes",
    "emails",
    "email_chunks",
    "email_attachments",
    "news_items",
    "news_stories",
)


def upgrade() -> None:
    """Upgrade schema."""
    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    # Left enabled on purpose: rolling back must not expose tables to the anon key.
