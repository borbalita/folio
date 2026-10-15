"""Expiry warning emails to the owner, sent through the Yahoo account ingest already uses."""

from __future__ import annotations

import math
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

import structlog

from app.config import settings

log = structlog.get_logger(__name__)

SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 465
TIMEOUT_SECONDS = 30


def accounts_url() -> str | None:
    redirect = settings.enable_banking_redirect_url
    return redirect.removesuffix("/callback") if redirect else None


def send_expiry_notice(bank: str, stage: str, valid_until: datetime | None, now: datetime) -> bool:
    """Send one warning; False when email isn't configured. SMTP errors propagate."""
    url = accounts_url()
    if not (settings.yahoo_email and settings.yahoo_app_password and url):
        log.warning("expiry_notice_skipped", bank=bank, stage=stage)
        return False
    if stage == "expired" or valid_until is None:
        subject = f"Folio: {bank} bank access has expired"
        lead = f"Folio can no longer read your {bank} account."
    else:
        days = max(1, math.ceil((valid_until - now) / timedelta(days=1)))
        subject = f"Folio: {bank} bank access expires in {days} days"
        lead = f"Folio's access to your {bank} account ends in {days} days."
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.yahoo_email
    message["To"] = settings.yahoo_email
    message.set_content(f"{lead}\n\nReconnect it on the accounts page:\n{url}\n")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_SECONDS) as smtp:
        smtp.login(settings.yahoo_email, settings.yahoo_app_password)
        smtp.send_message(message)
    log.info("expiry_notice_sent", bank=bank, stage=stage)
    return True
