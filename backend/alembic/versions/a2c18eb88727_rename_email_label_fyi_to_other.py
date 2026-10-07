"""rename email label fyi to other

Revision ID: a2c18eb88727
Revises: 2066068f8f06
Create Date: 2026-09-28 12:29:24.937017

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2c18eb88727"
down_revision: Union[str, Sequence[str], None] = "2066068f8f06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("ck_emails_label", "emails", type_="check")
    op.execute("UPDATE emails SET label = 'other' WHERE label = 'fyi'")
    op.alter_column(
        "emails",
        "label",
        existing_type=sa.String(length=32),
        server_default="other",
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_emails_label",
        "emails",
        "label IN ('needs_reply', 'promotional', 'newsletter', 'invoice', 'other', 'ai_newsletter')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_emails_label", "emails", type_="check")
    op.execute("UPDATE emails SET label = 'fyi' WHERE label = 'other'")
    op.alter_column(
        "emails",
        "label",
        existing_type=sa.String(length=32),
        server_default="fyi",
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_emails_label",
        "emails",
        "label IN ('needs_reply', 'promotional', 'newsletter', 'invoice', 'fyi', 'ai_newsletter')",
    )
