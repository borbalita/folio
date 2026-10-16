"""Extract invoices for invoice emails already stored.

Run from backend/: uv run python -m ingest.email.backfill_invoices [--all] [--detect]
"""

from __future__ import annotations

import argparse
from typing import Any

from langfuse import propagate_attributes
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.job_runs import run_job
from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel, EmailMessage
from app.database.models.finance.invoice import Invoice
from app.logging import configure_logging
from app.observability import configure_tracing, shutdown_tracing
from ingest.email.invoices import (
    Checker,
    Extractor,
    check_with_model,
    detect_invoices,
    extract_invoices,
)
from ingest.email.pipeline import open_session


def backfill(
    session: Session,
    *,
    everything: bool,
    extract: Extractor | None = None,
    check: Checker = check_with_model,
) -> dict[str, Any]:
    """Extract emails that have no invoices yet, or all with `everything`. Owner edits survive."""
    extracted = set(session.scalars(select(Invoice.email_id)))
    emails = session.scalars(
        select(EmailMessage)
        .where(EmailMessage.label == EmailLabel.INVOICE.value)
        .order_by(EmailMessage.sent_at)
    )
    counts = {"emails": 0, "invoices": 0, "invoice_failures": 0}
    for email in list(emails):
        if not everything and email.id in extracted:
            continue
        attachments = list(
            session.scalars(
                select(EmailAttachment)
                .where(EmailAttachment.email_id == email.id)
                .order_by(EmailAttachment.filename)
            )
        )
        outcome = extract_invoices(session, email, attachments, extract=extract, check=check)
        session.commit()
        counts["emails"] += 1
        counts["invoices"] += outcome.invoices
        counts["invoice_failures"] += int(outcome.failed)
    return counts


def detect(
    session: Session,
    *,
    extract: Extractor | None = None,
    check: Checker = check_with_model,
) -> dict[str, Any]:
    """Look for invoices in the PDFs of stored mail the labeller did not call an invoice."""
    skip = {EmailLabel.INVOICE.value, EmailLabel.AI_NEWSLETTER.value}
    emails = session.scalars(
        select(EmailMessage)
        .where(EmailMessage.label.not_in(skip))
        .order_by(EmailMessage.sent_at)
    )
    counts = {"checked": 0, "relabelled": 0, "invoices": 0}
    for email in [e for e in emails if e.label not in skip]:
        attachments = list(
            session.scalars(
                select(EmailAttachment)
                .where(EmailAttachment.email_id == email.id)
                .order_by(EmailAttachment.filename)
            )
        )
        if not any(a.content is not None for a in attachments):
            continue
        counts["checked"] += 1
        outcome = detect_invoices(session, email, attachments, extract=extract, check=check)
        if outcome is not None:
            counts["relabelled"] += 1
            counts["invoices"] += outcome.invoices
        session.commit()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-extract every invoice email, not only those without invoices",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Also look for invoices in the PDFs of mail not labelled as an invoice",
    )
    args = parser.parse_args(argv)
    configure_logging()
    configure_tracing()
    try:
        with propagate_attributes(tags=["ingest"]):

            def work() -> dict[str, Any]:
                session = open_session()
                try:
                    counts = backfill(session, everything=args.all)
                    if args.detect:
                        counts |= {f"detect_{k}": v for k, v in detect(session).items()}
                    return counts
                finally:
                    session.close()

            counts = run_job("invoice_backfill", work)
    finally:
        shutdown_tracing()
    print(", ".join(f"{name}: {value}" for name, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
