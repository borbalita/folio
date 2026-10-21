"""allow news chat threads

Revision ID: 2938db925e7d
Revises: bff323139bdf
Create Date: 2026-10-21 11:39:01.016552

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2938db925e7d'
down_revision: str | Sequence[str] | None = 'bff323139bdf'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate does not compare check constraints.
    op.drop_constraint('ck_chat_threads_agent', 'chat_threads', type_='check')
    op.create_check_constraint(
        'ck_chat_threads_agent',
        'chat_threads',
        "agent IN ('documents', 'email', 'finance', 'news')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_chat_threads_agent', 'chat_threads', type_='check')
    op.create_check_constraint(
        'ck_chat_threads_agent',
        'chat_threads',
        "agent IN ('documents', 'email', 'finance')",
    )
