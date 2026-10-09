"""Refuse to touch any database that isn't on this machine."""

from __future__ import annotations

from sqlalchemy.engine import make_url

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class NotLocalDatabaseError(RuntimeError):
    pass


def require_local_database(database_url: str) -> None:
    host = make_url(database_url).host
    if host not in LOCAL_HOSTS:
        raise NotLocalDatabaseError(
            f"refusing to run: database host {host!r} is not local. "
            "Run eval commands with `uv run --env-file .env.eval ...`."
        )
