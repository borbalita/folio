"""Deliver pending notifications to the owner's Telegram chat."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from datetime import time as clock
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models.notification import Notification, NotificationStatus
from app.notifications.store import telegram_enabled

log = structlog.get_logger(__name__)

API_URL = "https://api.telegram.org"
TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 5
# Telegram allows about one message a second to one chat.
PAUSE_SECONDS = 1.0
QUIET_FROM = clock(22, 0)
QUIET_UNTIL = clock(7, 0)


class _RedactToken(logging.Filter):
    """httpx logs each request URL at INFO, and the bot token is part of that URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        token = settings.telegram_bot_token
        if token:
            message = record.getMessage()
            if token in message:
                record.msg = message.replace(token, "<token>")
                record.args = ()
        return True


logging.getLogger("httpx").addFilter(_RedactToken())


def in_quiet_hours(now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(settings.email_timezone)).time()
    return local >= QUIET_FROM or local < QUIET_UNTIL


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def send_pending(
    session: Session, now: datetime, *, client: httpx.Client | None = None
) -> dict[str, int]:
    """Send pending rows oldest first. Failures stay in the table; nothing is raised."""
    counts = {"sent": 0, "failed": 0, "held": 0}
    if not telegram_enabled():
        return counts
    pending = list(
        session.scalars(
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING)
            .order_by(Notification.created_at, Notification.id)
        )
    )
    if in_quiet_hours(now):
        counts["held"] = len(pending)
        return counts
    url = f"{API_URL}/bot{settings.telegram_bot_token}/sendMessage"
    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        for index, row in enumerate(pending):
            if index:
                time.sleep(PAUSE_SECONDS)
            try:
                response = http.post(
                    url, json={"chat_id": settings.telegram_chat_id, "text": row.text}
                )
            except httpx.HTTPError as exc:
                _retry_later(row, type(exc).__name__, counts)
                session.commit()
                continue
            if response.status_code == 200:
                row.status = NotificationStatus.SENT
                row.sent_at = now
                counts["sent"] += 1
            elif _retryable(response.status_code):
                _retry_later(row, str(response.status_code), counts)
            else:
                # A wrong token or chat id fails every message the same way: stop here.
                row.status = NotificationStatus.FAILED
                row.attempts += 1
                row.last_error = str(response.status_code)
                counts["failed"] += 1
                session.commit()
                log.error("telegram_misconfigured", status=response.status_code)
                break
            session.commit()
    finally:
        if owned:
            http.close()
    return counts


def _retry_later(row: Notification, error: str, counts: dict[str, int]) -> None:
    row.attempts += 1
    row.last_error = error
    if row.attempts >= MAX_ATTEMPTS:
        row.status = NotificationStatus.FAILED
        counts["failed"] += 1
        log.warning("telegram_send_gave_up", kind=row.kind, error=error)
    else:
        log.warning("telegram_send_retry", kind=row.kind, error=error, attempts=row.attempts)
