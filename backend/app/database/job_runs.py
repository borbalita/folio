from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database.engine import get_session_factory
from app.database.models.job_run import JobRun, JobStatus

_ERROR_MAX_CHARS = 2000


def _open_default_session() -> Session:
    return get_session_factory()()


def run_job(
    job: str,
    work: Callable[[], dict[str, Any]],
    *,
    open_session: Callable[[], Session] = _open_default_session,
) -> dict[str, Any]:
    """Run `work` and record the outcome in `job_runs`.

    The RUNNING row is committed first so a crash mid-work still leaves a trace.
    """
    session = open_session()
    try:
        row = JobRun(job=job, status=JobStatus.RUNNING)
        session.add(row)
        session.commit()
        try:
            counts = work()
        except Exception as exc:
            row.status = JobStatus.FAILED
            row.error = f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_CHARS]
            row.finished_at = datetime.now(UTC)
            session.commit()
            raise
        row.status = JobStatus.OK
        row.counts = counts
        row.finished_at = datetime.now(UTC)
        session.commit()
        return counts
    finally:
        session.close()
