"""Yahoo ingest CLI. Run from backend/: uv run python -m ingest.email"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from app.config import settings
from app.logging import configure_logging
from ingest.email.pipeline import ingest_fetched, open_session
from ingest.email.yahoo import YahooImapAdapter


def missing_settings() -> list[str]:
    missing: list[str] = []
    if not settings.yahoo_email:
        missing.append("YAHOO_EMAIL")
    if not settings.yahoo_app_password:
        missing.append("YAHOO_APP_PASSWORD")
    if settings.email_agent_owner_user_id is None:
        missing.append("EMAIL_AGENT_OWNER_USER_ID")
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Yahoo INBOX into Supabase")
    parser.add_argument(
        "--limit", type=int, default=5, help="Newest messages to fetch; 0 means no cap"
    )
    parser.add_argument(
        "--since", type=date.fromisoformat, default=None, help="YYYY-MM-DD"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    if args.limit < 0:
        print("limit must be 0 or greater", file=sys.stderr)
        return 1
    missing = missing_settings()
    if missing:
        print(
            "Yahoo ingest needs " + ", ".join(missing) + ". Set them in backend/.env.",
            file=sys.stderr,
        )
        return 1

    adapter = YahooImapAdapter(
        settings.yahoo_email or "", settings.yahoo_app_password or ""
    )
    fetched = adapter.fetch(limit=args.limit, since=args.since)
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
