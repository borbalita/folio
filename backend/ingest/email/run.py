"""Yahoo ingest CLI. Run from backend/: uv run python -m ingest.email"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.config import settings
from app.database.job_runs import run_job
from app.logging import configure_logging
from ingest.email.pipeline import ingest_fetched, open_session, upsert_yahoo_mailbox
from ingest.email.yahoo import YahooImapAdapter


def missing_settings() -> list[str]:
    missing: list[str] = []
    if not settings.yahoo_email:
        missing.append("YAHOO_EMAIL")
    if not settings.yahoo_app_password:
        missing.append("YAHOO_APP_PASSWORD")
    if settings.email_agent_owner_user_id is None:
        missing.append("EMAIL_AGENT_OWNER_USER_ID")
    if not settings.typesafe_api_key:
        missing.append("TYPESAFE_API_KEY")
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Yahoo INBOX into Supabase")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Newest messages to fetch; default 5, 0 means no cap",
    )
    parser.add_argument(
        "--since", type=date.fromisoformat, default=None, help="YYYY-MM-DD"
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Cron mode: no cap, resume from the last sync, record a job_runs row",
    )
    return parser


def scheduled_since(last_synced_at: datetime | None, now: datetime) -> date:
    # One day of overlap covers mail that arrived mid-run; ingest is idempotent.
    if last_synced_at is None:
        return now.astimezone(UTC).date() - timedelta(days=7)
    return (last_synced_at - timedelta(days=1)).astimezone(UTC).date()


def run_scheduled() -> None:
    def work() -> dict[str, Any]:
        adapter = YahooImapAdapter(
            settings.yahoo_email or "", settings.yahoo_app_password or ""
        )
        session = open_session()
        try:
            mailbox = upsert_yahoo_mailbox(session)
            since = scheduled_since(mailbox.last_synced_at, datetime.now(UTC))
            session.commit()
            fetched = adapter.fetch(limit=0, since=since)
            summary = ingest_fetched(
                session,
                fetched.messages,
                uidvalidity=fetched.uidvalidity,
                highest_uid=fetched.highest_uid,
            )
        finally:
            session.close()
        print(summary.render())
        return dataclasses.asdict(summary)

    run_job("email_ingest", work)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.scheduled and (args.limit is not None or args.since is not None):
        parser.error("--scheduled sets its own limit and since")
    if args.limit is not None and args.limit < 0:
        print("limit must be 0 or greater", file=sys.stderr)
        return 1
    missing = missing_settings()
    if missing:
        print(
            "Yahoo ingest needs " + ", ".join(missing) + ". Set them in backend/.env.",
            file=sys.stderr,
        )
        return 1

    if args.scheduled:
        run_scheduled()
        return 0

    adapter = YahooImapAdapter(
        settings.yahoo_email or "", settings.yahoo_app_password or ""
    )
    limit = 5 if args.limit is None else args.limit
    fetched = adapter.fetch(limit=limit, since=args.since)
    session = open_session()
    try:
        summary = ingest_fetched(
            session,
            fetched.messages,
            uidvalidity=fetched.uidvalidity,
            highest_uid=fetched.highest_uid,
        )
    finally:
        session.close()
    print(summary.render())
    return 0
