"""Export the stored AI newsletters from the app database for the extraction benchmark.

The one eval command that reads the app database. It runs in a read-only transaction and
writes only to the gitignored evals/data/<version>/newsletters/. The files hold
per-recipient tracking links: never commit them.

Run: uv run python -m evals.news_export [--version news-v1]
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from email.header import decode_header, make_header
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.config import settings
from app.database.engine import get_session
from app.database.models.email.message import EmailLabel, EmailMessage
from evals.news_data import DEFAULT_NEWS_VERSION, Newsletter, news_dir


def decode_subject(value: str) -> str:
    """Older rows were stored with raw RFC 2047 words (fixed in ingest on feat/email-finish)."""
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeDecodeError, ValueError):
        return value


def to_newsletters(emails: Iterable[EmailMessage]) -> list[Newsletter]:
    ordered = sorted(emails, key=lambda email: (email.sent_at, email.message_id))
    zone = ZoneInfo(settings.email_timezone)
    return [
        Newsletter(
            key=f"n{index:02d}",
            source=email.newsletter_source or "unknown",
            sent_date=email.sent_at.astimezone(zone).date(),
            subject=decode_subject(email.subject),
            body=email.body,
            email_id=str(email.id),
        )
        for index, email in enumerate(ordered, start=1)
    ]


def _read_newsletters() -> list[Newsletter]:
    with get_session() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        emails = session.scalars(
            select(EmailMessage).where(
                EmailMessage.label == EmailLabel.AI_NEWSLETTER.value
            )
        ).all()
        return to_newsletters(emails)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_NEWS_VERSION)
    args = parser.parse_args()

    out = news_dir(args.version)
    if out.exists() and any(out.iterdir()):
        print(f"{out} already has files; delete it to export again.", file=sys.stderr)
        return 1

    newsletters = _read_newsletters()
    if not newsletters:
        print(
            "no ai_newsletter emails found; is DATABASE_URL the app database?",
            file=sys.stderr,
        )
        return 1

    out.mkdir(parents=True, exist_ok=True)
    for newsletter in newsletters:
        (out / f"{newsletter.key}.json").write_text(
            newsletter.model_dump_json(indent=2) + "\n"
        )

    by_source: dict[str, int] = {}
    for newsletter in newsletters:
        by_source[newsletter.source] = by_source.get(newsletter.source, 0) + 1
    first, last = newsletters[0].sent_date, newsletters[-1].sent_date
    print(
        f"exported {len(newsletters)} newsletters {by_source} from {first} to {last} into {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
