"""add chat thread story items

Revision ID: 9e2b6c41d7a8
Revises: 4d8e2a7f9b13
Create Date: 2026-11-05 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9e2b6c41d7a8"
down_revision: str | Sequence[str] | None = "4d8e2a7f9b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat_threads",
        sa.Column("story_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_threads", "story_items")
