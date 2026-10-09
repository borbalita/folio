import functools
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar

import pytest

from app.database.job_runs import run_job as real_run_job
from app.database.models.job_run import JobRun
from ingest.email.pipeline import IngestSummary
from ingest.email.run import main, missing_settings, scheduled_since
from ingest.email.yahoo import FetchResult


def test_missing_yahoo_settings_exit(monkeypatch) -> None:
    monkeypatch.setattr("ingest.email.run.settings.yahoo_email", None)
    monkeypatch.setattr("ingest.email.run.settings.yahoo_app_password", None)
    monkeypatch.setattr("ingest.email.run.settings.email_agent_owner_user_id", None)
    monkeypatch.setattr("ingest.email.run.settings.typesafe_api_key", None)
    assert main([]) == 1
    assert set(missing_settings()) == {
        "YAHOO_EMAIL",
        "YAHOO_APP_PASSWORD",
        "EMAIL_AGENT_OWNER_USER_ID",
        "TYPESAFE_API_KEY",
    }


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def test_since_is_one_day_before_last_sync() -> None:
    last = datetime(2026, 10, 8, 11, 0, tzinfo=UTC)
    assert scheduled_since(last, now=NOW) == date(2026, 10, 7)


def test_since_uses_utc_date_near_midnight() -> None:
    assert scheduled_since(datetime(2026, 10, 8, 0, 30, tzinfo=UTC), now=NOW) == date(
        2026, 10, 7
    )
    plus_two = datetime.fromisoformat("2026-10-08T01:30+02:00")
    assert scheduled_since(plus_two, now=NOW) == date(2026, 10, 6)


def test_never_synced_fetches_last_seven_days() -> None:
    assert scheduled_since(None, now=datetime(2026, 10, 8, 12, tzinfo=UTC)) == date(
        2026, 10, 1
    )


class _FakeIngestSession:
    def __init__(self) -> None:
        self.commits = 0
        self.closed = False

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


class _FakeJobSession:
    def __init__(self) -> None:
        self.added: list[JobRun] = []

    def add(self, row: JobRun) -> None:
        self.added.append(row)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeAdapter:
    fetch_calls: ClassVar[list[dict]] = []
    error: ClassVar[Exception | None] = None

    def __init__(self, *args) -> None:
        pass

    def fetch(self, **kwargs) -> FetchResult:
        type(self).fetch_calls.append(kwargs)
        if type(self).error is not None:
            raise type(self).error
        return FetchResult([], 1, None)


@pytest.fixture
def scheduled_env(monkeypatch):
    monkeypatch.setattr("ingest.email.run.settings.yahoo_email", "me@yahoo.com")
    monkeypatch.setattr("ingest.email.run.settings.yahoo_app_password", "pw")
    monkeypatch.setattr(
        "ingest.email.run.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    monkeypatch.setattr("ingest.email.run.settings.typesafe_api_key", "key")
    ingest_session = _FakeIngestSession()
    job_session = _FakeJobSession()
    _FakeAdapter.fetch_calls = []
    _FakeAdapter.error = None
    env = SimpleNamespace(
        ingest_session=ingest_session,
        job_session=job_session,
        summary=IngestSummary(fetched=0),
        jobs=[],
    )

    def set_last_synced(value):
        monkeypatch.setattr(
            "ingest.email.run.upsert_yahoo_mailbox",
            lambda session: SimpleNamespace(last_synced_at=value),
        )

    def fake_run_job(job, work):
        env.jobs.append(job)
        return work()

    set_last_synced(None)
    env.set_last_synced = set_last_synced
    monkeypatch.setattr("ingest.email.run.YahooImapAdapter", _FakeAdapter)
    monkeypatch.setattr("ingest.email.run.open_session", lambda: ingest_session)
    monkeypatch.setattr("ingest.email.run.ingest_fetched", lambda *a, **k: env.summary)
    monkeypatch.setattr("ingest.email.run.run_job", fake_run_job)
    env.use_real_run_job = lambda: monkeypatch.setattr(
        "ingest.email.run.run_job",
        functools.partial(real_run_job, open_session=lambda: job_session),
    )
    return env


def test_scheduled_run_fetches_since_last_sync_with_no_cap(scheduled_env) -> None:
    last = datetime.now(UTC) - timedelta(hours=1)
    scheduled_env.set_last_synced(last)

    assert main(["--scheduled"]) == 0

    assert _FakeAdapter.fetch_calls == [
        {"limit": 0, "since": (last - timedelta(days=1)).astimezone(UTC).date()}
    ]
    assert scheduled_env.jobs == ["email_ingest"]
    assert scheduled_env.ingest_session.closed


def test_scheduled_run_without_mailbox_fetches_seven_days(scheduled_env) -> None:
    assert main(["--scheduled"]) == 0

    expected = datetime.now(UTC).date() - timedelta(days=7)
    assert _FakeAdapter.fetch_calls == [{"limit": 0, "since": expected}]


def test_scheduled_run_records_counts(scheduled_env) -> None:
    scheduled_env.use_real_run_job()
    scheduled_env.summary = IngestSummary(new=3)

    assert main(["--scheduled"]) == 0

    (row,) = scheduled_env.job_session.added
    assert row.status == "ok"
    assert row.counts["new"] == 3


def test_scheduled_run_failure_is_logged_and_raised(scheduled_env) -> None:
    scheduled_env.use_real_run_job()
    _FakeAdapter.error = OSError("imap down")

    with pytest.raises(OSError):
        main(["--scheduled"])

    (row,) = scheduled_env.job_session.added
    assert row.status == "failed"
    assert row.error == "OSError: imap down"
    assert scheduled_env.ingest_session.closed


@pytest.mark.parametrize("extra", [["--limit", "3"], ["--since", "2026-10-01"]])
def test_scheduled_rejects_limit_and_since(extra) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--scheduled", *extra])
    assert exc.value.code == 2
