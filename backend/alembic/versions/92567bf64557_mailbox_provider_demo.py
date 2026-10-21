"""mailbox provider demo

Revision ID: 92567bf64557
Revises: bff323139bdf
Create Date: 2026-10-21 11:31:13.626980

Downgrade requires deleting provider='demo' mailboxes first.

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92567bf64557"
down_revision: str | Sequence[str] | None = "bff323139bdf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("ck_mailboxes_provider", "mailboxes", type_="check")
    op.create_check_constraint(
        "ck_mailboxes_provider", "mailboxes", "provider IN ('yahoo', 'gmail', 'demo')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_mailboxes_provider", "mailboxes", type_="check")
    op.create_check_constraint(
        "ck_mailboxes_provider", "mailboxes", "provider IN ('yahoo', 'gmail')"
    )
