"""add transactions

Revision ID: d81e5a3c2f60
Revises: 9c8e4850a3a6
Create Date: 2026-10-14 20:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd81e5a3c2f60'
down_revision: str | Sequence[str] | None = '9c8e4850a3a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# RLS with no policies: the anon key reads nothing; the backend's service role bypasses RLS.
RLS_TABLES = ("transactions",)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('transactions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('booking_date', sa.Date(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('counterparty_name', sa.Text(), nullable=True),
    sa.Column('counterparty_iban', sa.Text(), nullable=True),
    sa.Column('remittance', sa.Text(), nullable=False),
    sa.Column('bank_code', sa.Text(), nullable=True),
    sa.Column('entry_reference', sa.Text(), nullable=True),
    sa.Column('dedup_key', sa.Text(), nullable=False),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'dedup_key', name='uq_transactions_account_id_dedup_key')
    )
    op.create_index('ix_transactions_account_id_booking_date', 'transactions', ['account_id', 'booking_date'], unique=False)
    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_transactions_account_id_booking_date', table_name='transactions')
    op.drop_table('transactions')
