"""add news item notes

Revision ID: 4d8e2a7f9b13
Revises: 01b8354147e4
Create Date: 2026-11-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4d8e2a7f9b13"
down_revision: str | Sequence[str] | None = "01b8354147e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# RLS with no policies: the anon key reads nothing; the backend's service role bypasses RLS.
RLS_TABLES = ("news_item_notes",)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "news_item_notes",
        sa.Column("email_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("security", sa.Boolean(), nullable=True),
        sa.Column("alert_status", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "alert_status IS NULL OR alert_status IN ('new', 'update', 'repeat')",
            name="ck_news_item_notes_alert_status",
        ),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("email_id", "position", name="pk_news_item_notes"),
    )
    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("news_item_notes")
