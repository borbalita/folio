from __future__ import annotations

import importlib.util
from pathlib import Path

from app.database.models.chat.thread import ChatThread

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_model_allows_news_threads() -> None:
    [check] = [
        constraint
        for constraint in ChatThread.__table__.constraints
        if constraint.name == "ck_chat_threads_agent"
    ]
    assert "'news'" in str(check.sqltext)


def test_a_migration_allows_news_threads() -> None:
    path = next(VERSIONS.glob("*_allow_news_chat_threads.py"))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "'news'" in path.read_text()
    assert callable(module.upgrade) and callable(module.downgrade)
