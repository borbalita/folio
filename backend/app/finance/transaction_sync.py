"""Pull booked transactions from every connected account into `transactions`."""

from __future__ import annotations

import asyncio
import smtplib
import uuid
from datetime import UTC, date, datetime, timedelta

import structlog

from app.database import bank_connections, matches, transactions
from app.database.job_runs import run_job
from app.finance import enable_banking, notify
from app.finance.expiry import due_notice

log = structlog.get_logger(__name__)

# Banks can book late; re-reading a week costs nothing because inserts are deduplicated.
OVERLAP = timedelta(days=7)
FIRST_SYNC = timedelta(days=90)


class BankSyncFailed(Exception):
    """At least one account failed; the others were stored."""


async def sync_all(
    user_id: uuid.UUID,
    *,
    today: date,
    psu_headers: dict[str, str] | None = None,
) -> dict[str, int]:
    now = datetime.now(UTC)
    accounts, skipped = bank_connections.sync_targets(user_id, now)
    latest = transactions.latest_booking_dates([a.id for a in accounts])
    counts = {
        "accounts": len(accounts),
        "fetched": 0,
        "added": 0,
        "skipped": skipped,
        "unparsed": 0,
        "expired": 0,
        "notices": 0,
    }
    failures: list[str] = []
    invalidated: set[uuid.UUID] = set()
    for account in accounts:
        since = latest[account.id] - OVERLAP if account.id in latest else today - FIRST_SYNC
        try:
            txs, unparsed = await enable_banking.fetch_transactions(
                account.uid, since, psu_headers=psu_headers
            )
        except enable_banking.EnableBankingError as exc:
            if exc.session_invalid:
                # Expected once consent lapses or is revoked: only a reconnect helps.
                log.warning("bank_session_invalid", bank=account.bank, code=exc.code)
                if account.connection_id not in invalidated:
                    bank_connections.mark_invalid(account.connection_id, now)
                    invalidated.add(account.connection_id)
                continue
            log.warning(
                "bank_sync_account_failed", bank=account.bank, status=exc.status, code=exc.code
            )
            failures.append(f"{account.bank}: {exc}")
            continue
        counts["fetched"] += len(txs)
        counts["unparsed"] += unparsed
        counts["added"] += transactions.store(account.id, txs)
    counts["expired"] = len(invalidated)
    counts["notices"] = send_due_notices(user_id, now)
    # Also after a partial failure: what was stored may pay an open invoice.
    counts.update(matches.match_for_user(user_id, now))
    if failures:
        raise BankSyncFailed("; ".join(failures))
    return counts


def send_due_notices(user_id: uuid.UUID, now: datetime) -> int:
    """Email each warning stage once; a failed send is retried on the next sync."""
    sent = 0
    for state in bank_connections.connection_states(user_id):
        stage = due_notice(state.valid_until, state.invalidated_at, state.expiry_notice, now)
        if stage is None:
            continue
        try:
            delivered = notify.send_expiry_notice(state.bank, stage, state.valid_until, now)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning(
                "expiry_notice_failed", bank=state.bank, stage=stage, error=type(exc).__name__
            )
            continue
        if delivered:
            bank_connections.record_notice(state.id, stage)
            sent += 1
    return sent


def run_bank_sync(
    user_id: uuid.UUID, psu_headers: dict[str, str] | None = None
) -> dict[str, int]:
    """Blocking; the API calls it through `asyncio.to_thread`."""
    return run_job(
        "bank_sync",
        lambda: asyncio.run(
            sync_all(user_id, today=datetime.now(UTC).date(), psu_headers=psu_headers)
        ),
    )
