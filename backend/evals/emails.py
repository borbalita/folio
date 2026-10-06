"""Build .eml files from scenario emails and check that their bodies carry the facts."""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import format_datetime, formataddr

from evals.scenario import Fact, Scenario, ScenarioEmail
from ingest.email.parse import normalize_whitespace


def message_id(email_key: str) -> str:
    return f"{email_key}@folio-eval.example"


def build_eml(scenario: Scenario, email: ScenarioEmail, body: str) -> bytes:
    """Headers come from the scenario, so sender, date, and subject are exact by construction."""
    sender = next(s for s in scenario.senders if s.key == email.sender_key)
    message = EmailMessage()
    message["From"] = formataddr((sender.name, sender.address))
    message["To"] = formataddr((scenario.owner_name, scenario.owner_address))
    message["Date"] = format_datetime(email.sent_at)
    message["Subject"] = email.subject
    message["Message-ID"] = f"<{message_id(email.key)}>"
    if email.in_reply_to is not None:
        message["In-Reply-To"] = f"<{message_id(email.in_reply_to)}>"
    subtype = "html" if email.body_format == "html" else "plain"
    message.set_content(body, subtype=subtype)
    return bytes(message)


def missing_facts(body: str, facts: list[Fact]) -> list[Fact]:
    """Facts whose value does not appear in the parsed body (case and spacing ignored)."""
    haystack = _normalize(body)
    return [fact for fact in facts if _normalize(fact.value) not in haystack]


def _normalize(text: str) -> str:
    return normalize_whitespace(text).casefold()
