"""key news notifications by article

Revision ID: bff323139bdf
Revises: d92e6ad10cbb
Create Date: 2026-10-19 21:35:54.321195

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'bff323139bdf'
down_revision: str | Sequence[str] | None = 'd92e6ad10cbb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
