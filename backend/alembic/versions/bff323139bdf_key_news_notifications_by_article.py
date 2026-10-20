"""key news notifications by article

Revision ID: bff323139bdf
Revises: d92e6ad10cbb
Create Date: 2026-10-19 21:35:54.321195

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bff323139bdf'
down_revision: str | Sequence[str] | None = 'd92e6ad10cbb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# News notifications were keyed by news item id, but re-embedding recreates items with new
# ids. Re-key them by the item's newsletter email and position, which survive it.
REKEY = """
INSERT INTO notifications (id, key, kind, status, text, attempts, last_error, created_at, sent_at)
SELECT DISTINCT ON (k.key) gen_random_uuid(), k.key, n.kind, n.status, n.text, n.attempts,
       n.last_error, n.created_at, n.sent_at
FROM notifications n
JOIN news_items i ON n.key = 'news:' || i.id
CROSS JOIN LATERAL (SELECT 'news:' || i.email_id || ':' || i.position AS key) k
ORDER BY k.key, n.created_at
ON CONFLICT (key) DO NOTHING
"""
DROP_ITEM_KEYS = """
DELETE FROM notifications
WHERE key ~ '^news:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(REKEY)
    op.execute(DROP_ITEM_KEYS)


def downgrade() -> None:
    """Downgrade schema."""
    # Not reversible: the item ids of re-keyed rows are not kept. The rows stay valid as is.
