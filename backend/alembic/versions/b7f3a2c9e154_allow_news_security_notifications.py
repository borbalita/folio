"""allow news security notifications

Revision ID: b7f3a2c9e154
Revises: 9e2b6c41d7a8
Create Date: 2026-11-05 18:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f3a2c9e154"
down_revision: str | Sequence[str] | None = "9e2b6c41d7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "kind IN ('invoice_new', 'invoice_due', 'news_big', 'news_security')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Security rows would violate the narrower constraint.
    op.execute("DELETE FROM notifications WHERE kind = 'news_security'")
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "kind IN ('invoice_new', 'invoice_due', 'news_big')",
    )
