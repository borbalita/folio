import uuid
from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.demo import reset
from app.demo.accounts import DemoAccounts

USER = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
ACCOUNTS = DemoAccounts(
    mailbox_id=uuid.uuid4(),
    account_id=uuid.uuid4(),
    card_account_id=uuid.uuid4(),
    wallet_account_id=uuid.uuid4(),
)
TODAY = date(2026, 10, 21)


class _Recorder:
    def __init__(self, fail_on_add: bool = False) -> None:
        self.statements: list[str] = []
        self.added: list[object] = []
        self.commits = 0
        self.fail_on_add = fail_on_add
        self.pending: list[str] = []
        self.flushes: list[list[str]] = []

    def execute(self, statement):
        compiled = statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        self.statements.append(str(compiled))

    def add_all(self, rows) -> None:
        if self.fail_on_add:
            raise RuntimeError("disk full")
        self.added += list(rows)
        self.pending += [type(row).__name__ for row in rows]

    def flush(self) -> None:
        self.flushes.append(sorted(set(self.pending)))
        self.pending = []

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture(autouse=True)
def demo_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reset, "ensure_demo_accounts", lambda session, user_id: ACCOUNTS
    )


def test_reset_deletes_only_the_demo_users_rows() -> None:
    session = _Recorder()

    reset.reset_demo(session, USER, email="demo@example.com", today=TODAY)

    assert len(session.statements) == 6
    lock, stories, emails, transactions, connections, threads = session.statements
    # A second reset waits for the first, so two base states can't pile up.
    assert lock.startswith("SELECT mailboxes.id")
    assert f"mailboxes.id = '{ACCOUNTS.mailbox_id}'" in lock
    assert lock.endswith("FOR UPDATE")
    # Stories aren't removed by the email cascade, so they go first, found through the
    # demo mailbox's items.
    assert stories.startswith("DELETE FROM news_stories")
    assert "news_items.story_id" in stories
    assert f"emails.mailbox_id = '{ACCOUNTS.mailbox_id}'" in stories
    assert session.statements.index(stories) < session.statements.index(emails)
    assert emails.startswith("DELETE FROM emails")
    assert f"emails.mailbox_id = '{ACCOUNTS.mailbox_id}'" in emails
    assert transactions.startswith("DELETE FROM transactions")
    assert "transactions.account_id IN" in transactions
    for account_id in ACCOUNTS.account_ids:
        assert f"'{account_id}'" in transactions
    # The old single "Demo Bank" goes, with its account and transactions by cascade.
    assert connections.startswith("DELETE FROM bank_connections")
    assert f"bank_connections.user_id = '{USER}'" in connections
    assert (
        "bank_connections.bank NOT IN ('Spreeufer Bank', 'Kiez Direkt', 'TalerPay')"
        in connections
    )
    assert threads.startswith("DELETE FROM chat_threads")
    assert f"chat_threads.user_id = '{USER}'" in threads
    assert "chat_threads.agent = 'finance'" in threads
    for statement in session.statements[1:]:
        assert "WHERE" in statement
        # Invoices, matches and drafts go with their email through the cascades.
        for table in ("invoices", "invoice_matches", "payment_drafts"):
            assert f"DELETE FROM {table}" not in statement


def test_reset_writes_the_base_state_and_does_not_commit() -> None:
    session = _Recorder()

    counts = reset.reset_demo(session, USER, email="demo@example.com", today=TODAY)

    assert counts["invoices"] == 9
    assert counts["mails"] == 40
    assert 34 <= counts["transactions"] <= 40
    assert len(session.added) > counts["invoices"] + counts["transactions"]
    assert session.commits == 0


def test_run_reset_commits_once(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Recorder()

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(reset, "get_session", fake_session)

    reset.run_reset(USER, "demo@example.com", TODAY)

    assert session.commits == 1


def test_run_reset_keeps_the_old_state_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Recorder(fail_on_add=True)

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(reset, "get_session", fake_session)

    with pytest.raises(RuntimeError):
        reset.run_reset(USER, "demo@example.com", TODAY)
    # get_session closes without a commit, which rolls the deletes back.
    assert session.commits == 0


@pytest.fixture
def quiet_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    # configure_logging() turns structlog's logger cache back on (tests/conftest.py turns
    # it off), so later tests' capture_logs would miss loggers first used after this one.
    monkeypatch.setattr(reset, "configure_logging", lambda: None)


@pytest.mark.usefixtures("quiet_logging")
def test_command_needs_a_demo_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", None)

    assert reset.main() == 1
    assert "Set DEMO_USER_ID first." in capsys.readouterr().err


@pytest.mark.usefixtures("quiet_logging")
def test_command_needs_a_signed_in_demo_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", USER)
    monkeypatch.setattr(reset, "demo_user_email", lambda user_id: None)
    monkeypatch.setattr(reset, "run_reset", lambda *a, **k: pytest.fail("not called"))

    assert reset.main() == 1
    assert "Sign in once as the demo user first." in capsys.readouterr().err


@pytest.mark.usefixtures("quiet_logging")
def test_command_resets_and_prints_the_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", USER)
    monkeypatch.setattr(reset, "demo_user_email", lambda user_id: "demo@example.com")
    monkeypatch.setattr(
        reset, "run_reset", lambda user_id, email: {"invoices": 9, "transactions": 36}
    )

    assert reset.main() == 0
    assert "invoices: 9, transactions: 36" in capsys.readouterr().out


def test_reset_flushes_parents_before_children() -> None:
    # No relationships are mapped, so one flush would insert in class-name order.
    session = _Recorder()

    reset.reset_demo(session, USER, email="demo@example.com", today=TODAY)

    assert session.flushes == [
        ["EmailMessage"],
        ["EmailMessage"],
        ["EmailMessage"],
        ["EmailChunk"],
        ["NewsStory"],
        ["NewsItem"],
        ["EmailAttachment"],
        ["Invoice"],
        ["Transaction"],
        ["InvoiceMatch"],
    ]
