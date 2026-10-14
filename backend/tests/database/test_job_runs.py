import pytest

from app.database.job_runs import run_job
from app.database.models.job_run import JobRun


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[JobRun] = []
        self.commits = 0
        self.closed = False

    def add(self, row: JobRun) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


def test_successful_run_records_ok_and_counts() -> None:
    session = _FakeSession()

    result = run_job("email_ingest", lambda: {"new": 2}, open_session=lambda: session)

    assert result == {"new": 2}
    (row,) = session.added
    assert row.job == "email_ingest"
    assert row.status == "ok"
    assert row.counts == {"new": 2}
    assert row.finished_at is not None
    assert row.error is None
    assert session.closed


def test_failed_run_records_error_and_reraises() -> None:
    session = _FakeSession()

    def work() -> dict[str, int]:
        raise RuntimeError("imap down")

    with pytest.raises(RuntimeError):
        run_job("email_ingest", work, open_session=lambda: session)

    (row,) = session.added
    assert row.status == "failed"
    assert row.error == "RuntimeError: imap down"
    assert row.counts is None
    assert row.finished_at is not None
    assert session.closed


def test_running_row_is_committed_before_work() -> None:
    session = _FakeSession()
    seen: list[tuple[int, str]] = []

    def work() -> dict[str, int]:
        seen.append((session.commits, session.added[0].status))
        return {}

    run_job("email_ingest", work, open_session=lambda: session)

    assert seen == [(1, "running")]


def test_long_error_is_truncated() -> None:
    session = _FakeSession()

    def work() -> dict[str, int]:
        raise RuntimeError("x" * 5000)

    with pytest.raises(RuntimeError):
        run_job("email_ingest", work, open_session=lambda: session)

    assert len(session.added[0].error or "") == 2000


def test_last_started_returns_newest(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from sqlalchemy.dialects import postgresql

    from app.database import job_runs

    newest = datetime(2026, 10, 14, 12, tzinfo=UTC)
    session = MagicMock()
    session.scalar.return_value = newest

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(job_runs, "get_session", fake_get_session)

    assert job_runs.last_started("bank_sync") == newest
    sql = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "max(job_runs.started_at)" in sql
    assert "job_runs.job = " in sql
