"""Pull booked transactions from every connected account into `transactions`."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import structlog

from app.database import bank_connections, transactions
from app.database.job_runs import run_job
from app.finance import enable_banking

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
    }
    failures: list[str] = []
    for account in accounts:
        since = latest[account.id] - OVERLAP if account.id in latest else today - FIRST_SYNC
        try:
            txs, unparsed = await enable_banking.fetch_transactions(
                account.uid, since, psu_headers=psu_headers
            )
        except enable_banking.EnableBankingError as exc:
            log.warning("bank_sync_account_failed", bank=account.bank, status=exc.status)
            failures.append(f"{account.bank}: {exc}")
            continue
        counts["fetched"] += len(txs)
        counts["unparsed"] += unparsed
        counts["added"] += transactions.store(account.id, txs)
    if failures:
        raise BankSyncFailed("; ".join(failures))
    return counts


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
