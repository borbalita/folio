"""Mark security stories among older newsletter items, for the dashboard's badges.

Run from backend/: uv run python -m ingest.news_security --days 30

It writes the security mark only and never an alert status, so it sends nothing. The last two
days are left to the notify step, which alerts on them.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.logging import configure_logging
from app.notifications import security, store
from ingest.email.pipeline import open_session


def backfill(session: Session, *, days: int, today: date) -> dict[str, int]:
    """Classify unclassified items day by day, oldest day first, one call per day."""
    counts = {"days": 0, "classified": 0, "failed_days": 0}
    first = today - timedelta(days=days)
    last = today - store.NEWS_LOOKBACK
    day = first
    while day < last:
        counts["days"] += 1
        candidates = store.load_unclassified(session, day, day + timedelta(days=1))
        # No alert history: statuses are not kept, so there is nothing to compare with.
        results = security.classify(candidates, []) if candidates else []
        if results is None:
            counts["failed_days"] += 1
        else:
            store.save_security_only(session, results)
            session.commit()
            counts["classified"] += len(results)
        day += timedelta(days=1)
    return counts


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=_positive, required=True, help="How many days back")
    args = parser.parse_args(argv)
    configure_logging()
    today = datetime.now(ZoneInfo(settings.email_timezone)).date()
    session = open_session()
    try:
        print(backfill(session, days=args.days, today=today))
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
