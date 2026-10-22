"""demo newsletter sources

Revision ID: 01b8354147e4
Revises: 92567bf64557
Create Date: 2026-10-22 19:06:43.845262

Downgrade requires deleting emails and news_items rows whose newsletter source
is demo_tensor or demo_detective first.

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "01b8354147e4"
down_revision: str | Sequence[str] | None = "92567bf64557"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REAL = "'tldr', 'alpha_signal'"
ALL = "'tldr', 'alpha_signal', 'demo_tensor', 'demo_detective'"


def _replace(sources: str) -> None:
    op.drop_constraint("ck_emails_newsletter_source", "emails", type_="check")
    op.create_check_constraint(
        "ck_emails_newsletter_source",
        "emails",
        f"newsletter_source IS NULL OR newsletter_source IN ({sources})",
    )
    op.drop_constraint("ck_news_items_source", "news_items", type_="check")
    op.create_check_constraint(
        "ck_news_items_source", "news_items", f"source IN ({sources})"
    )


def upgrade() -> None:
    """Upgrade schema."""
    _replace(ALL)


def downgrade() -> None:
    """Downgrade schema."""
    _replace(REAL)
