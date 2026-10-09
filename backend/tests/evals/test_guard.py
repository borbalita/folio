from __future__ import annotations

import pytest

from evals.guard import NotLocalDatabaseError, require_local_database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:postgres@localhost:5433/folio_eval",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/folio_eval",
    ],
)
def test_local_database_is_allowed(url: str) -> None:
    require_local_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:secret@db.abcdefgh.supabase.co:5432/postgres",
        "postgresql://postgres@/folio_eval",
    ],
)
def test_other_databases_are_refused(url: str) -> None:
    with pytest.raises(NotLocalDatabaseError, match="not local"):
        require_local_database(url)
