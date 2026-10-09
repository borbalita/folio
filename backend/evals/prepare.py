"""Rebuild the eval database: empty it, migrate, seed fake users, and ingest a data version.

Run: uv run --env-file .env.eval python -m evals.prepare [--version v1]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import BACKEND_ROOT, settings
from app.database.engine import get_engine, get_session
from app.database.models.email.chunk import EmailChunk
from app.database.models.email.message import EmailMessage
from evals.dataset import (
    DEFAULT_VERSION,
    IdMap,
    StoredEmailIds,
    data_dir,
    id_map_path,
    load_scenario,
)
from evals.emails import message_id
from evals.fixtures import A_ACTIVE, seed_users_and_mailboxes
from evals.guard import NotLocalDatabaseError, require_local_database
from ingest.email.parse import ParsedMessage, parse_rfc822
from ingest.email.pipeline import ingest_messages


@dataclass(frozen=True, slots=True)
class LabelMismatch:
    email_key: str
    expected: str
    stored: str | None


def reset_schema() -> None:
    with get_engine().begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def migrate() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


def parse_emails(version: str, keys: list[str]) -> list[ParsedMessage]:
    emails_dir = data_dir(version) / "emails"
    return [
        parse_rfc822(
            (emails_dir / f"{key}.eml").read_bytes(),
            provider_message_id=key,
            folder="INBOX",
        )
        for key in keys
    ]


def label_mismatches(
    expected: dict[str, str], stored: dict[str, str]
) -> list[LabelMismatch]:
    """Every scenario email whose stored label differs, or that was never stored."""
    return [
        LabelMismatch(email_key=key, expected=label, stored=stored.get(key))
        for key, label in sorted(expected.items())
        if stored.get(key) != label
    ]


StoredRow = tuple[str, UUID, str, UUID]
"""message_id, email_id, label, chunk_id; one row per chunk, in chunk order."""


def stored_ids(
    session: Session, keys: list[str]
) -> dict[str, tuple[StoredEmailIds, str]]:
    """Scenario key -> (database IDs, stored label) for the emails in user A's active mailbox."""
    rows = session.execute(
        select(
            EmailMessage.message_id, EmailMessage.id, EmailMessage.label, EmailChunk.id
        )
        .join(EmailChunk, EmailChunk.email_id == EmailMessage.id)
        .where(
            EmailMessage.mailbox_id == A_ACTIVE.id,
            EmailMessage.message_id.in_([message_id(key) for key in keys]),
        )
        .order_by(EmailMessage.message_id, EmailChunk.chunk_index)
    ).all()
    return group_stored_rows([tuple(row) for row in rows], keys)


def group_stored_rows(
    rows: list[StoredRow], keys: list[str]
) -> dict[str, tuple[StoredEmailIds, str]]:
    key_by_message_id = {message_id(key): key for key in keys}
    found: dict[str, tuple[StoredEmailIds, str]] = {}
    for mid, email_id, label, chunk_id in rows:
        ids, _ = found.setdefault(
            key_by_message_id[mid],
            (StoredEmailIds(email_id=email_id, chunk_ids=[]), label),
        )
        ids.chunk_ids.append(chunk_id)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args()
    try:
        require_local_database(settings.database_url)
    except NotLocalDatabaseError as exc:
        print(exc, file=sys.stderr)
        return 1

    scenario = load_scenario(args.version)
    keys = [email.key for email in scenario.emails]
    reset_schema()
    migrate()
    with get_session() as session:
        seed_users_and_mailboxes(session)
        print("eval database migrated and seeded")
        summary = ingest_messages(
            session, A_ACTIVE.id, parse_emails(args.version, keys)
        )
        print(summary.render())
        found = stored_ids(session, keys)

    missing = sorted(set(keys) - set(found))
    if missing:
        print(f"not stored: {', '.join(missing)}", file=sys.stderr)
        return 1
    id_map = IdMap(
        version=args.version, emails={key: ids for key, (ids, _) in found.items()}
    )
    path = id_map_path(args.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(id_map.model_dump_json(indent=2) + "\n")
    print(f"id map: {path}")

    expected = {email.key: email.label for email in scenario.emails}
    mismatches = label_mismatches(
        expected, {key: label for key, (_, label) in found.items()}
    )
    print(
        f"stored labels: {len(keys) - len(mismatches)}/{len(keys)} match the scenario"
    )
    for mismatch in mismatches:
        email = next(e for e in scenario.emails if e.key == mismatch.email_key)
        borderline = (
            " (borderline)"
            if any(t.kind == "borderline_label" for t in email.traps)
            else ""
        )
        print(
            f"  {mismatch.email_key}: expected {mismatch.expected}, stored {mismatch.stored}{borderline}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
