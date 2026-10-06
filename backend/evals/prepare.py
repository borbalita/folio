"""Rebuild the eval database: empty it, migrate, and seed fake users and mailboxes."""

from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import BACKEND_ROOT, settings
from app.database.engine import get_engine, get_session
from evals.fixtures import seed_users_and_mailboxes
from evals.guard import NotLocalDatabaseError, require_local_database


def reset_schema() -> None:
    with get_engine().begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def migrate() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


def main() -> int:
    try:
        require_local_database(settings.database_url)
    except NotLocalDatabaseError as exc:
        print(exc, file=sys.stderr)
        return 1
    reset_schema()
    migrate()
    with get_session() as session:
        seed_users_and_mailboxes(session)
    print("eval database ready: migrated and seeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
