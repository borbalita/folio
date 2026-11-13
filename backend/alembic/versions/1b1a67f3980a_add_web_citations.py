"""add web citations

Revision ID: 1b1a67f3980a
Revises: b7f3a2c9e154
Create Date: 2026-11-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1b1a67f3980a"
down_revision: str | Sequence[str] | None = "b7f3a2c9e154"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("email_citations", sa.Column("web_url", sa.Text(), nullable=True))
    op.add_column("email_citations", sa.Column("web_title", sa.Text(), nullable=True))
    # Autogenerate doesn't compare check constraints.
    op.drop_constraint("ck_email_citations_one_target", "email_citations", type_="check")
    op.create_check_constraint(
        "ck_email_citations_one_target",
        "email_citations",
        "num_nonnulls(email_chunk_id, news_item_id, web_url) = 1",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Web rows would violate the narrower constraint.
    op.execute("DELETE FROM email_citations WHERE web_url IS NOT NULL")
    op.drop_constraint("ck_email_citations_one_target", "email_citations", type_="check")
    op.create_check_constraint(
        "ck_email_citations_one_target",
        "email_citations",
        "(email_chunk_id IS NOT NULL) <> (news_item_id IS NOT NULL)",
    )
    op.drop_column("email_citations", "web_title")
    op.drop_column("email_citations", "web_url")
