"""allow finance chat threads

Revision ID: c3f1d9a47b20
Revises: 5a471474ec22
Create Date: 2026-10-08 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f1d9a47b20'
down_revision: str | Sequence[str] | None = '5a471474ec22'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('ck_chat_threads_agent', 'chat_threads', type_='check')
    op.create_check_constraint(
        'ck_chat_threads_agent',
        'chat_threads',
        "agent IN ('documents', 'email', 'finance')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_chat_threads_agent', 'chat_threads', type_='check')
    op.create_check_constraint(
        'ck_chat_threads_agent',
        'chat_threads',
        "agent IN ('documents', 'email')",
    )
