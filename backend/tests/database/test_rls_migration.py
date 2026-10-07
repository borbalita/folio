from __future__ import annotations

import importlib.util
from pathlib import Path

from app.database.models import Base

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _rls_tables() -> set[str]:
    """Union of `RLS_TABLES` declared by any migration."""
    tables: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tables.update(getattr(module, "RLS_TABLES", ()))
    return tables


def test_every_model_table_gets_rls() -> None:
    missing = set(Base.metadata.tables) - _rls_tables()
    assert not missing, (
        f"Enable RLS for {sorted(missing)} in the migration that creates them "
        "and list them in that migration's RLS_TABLES."
    )


def test_alembic_version_gets_rls() -> None:
    assert "alembic_version" in _rls_tables()
