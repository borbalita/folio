from __future__ import annotations

from evals.emails import build_eml, missing_facts
from evals.scenario import Fact, Scenario
from ingest.email.parse import parse_rfc822
from tests.evals.conftest import make_email

FACTS = [
    Fact(name="amount", value="€1,240.00"),
    Fact(name="due date", value="14 October 2026"),
]


def test_present_facts_pass_ignoring_case_and_spacing() -> None:
    body = "Please pay €1,240.00 by  14 october\n2026. Thanks!"

    assert missing_facts(body, FACTS) == []


def test_changed_or_absent_facts_are_reported() -> None:
    body = "Please pay €1.240,00 soon."

    assert missing_facts(body, FACTS) == FACTS


def test_eml_round_trips_through_the_production_parser(
    valid_scenario: Scenario,
) -> None:
    email = make_email(
        "e07", "invoice", subject="Your October invoice", in_reply_to="e03"
    )

    raw = build_eml(valid_scenario, email, "Amount due: €1,240.00")
    parsed = parse_rfc822(raw, provider_message_id="e07", folder="INBOX")

    assert parsed.message_id == "e07@folio-eval.example"
    assert parsed.subject == "Your October invoice"
    assert parsed.from_address == "hello@shop.example"
    assert parsed.to_addresses == ["anna@example.com"]
    assert parsed.sent_at == email.sent_at
    assert parsed.body == "Amount due: €1,240.00"
    assert b"In-Reply-To: <e03@folio-eval.example>" in raw


def test_html_facts_are_checked_on_the_parsed_text(valid_scenario: Scenario) -> None:
    email = make_email("e08", "invoice", body_format="html")
    html = "<html><body><p>Pay <b>€1,240.00</b> by 14 October 2026.</p></body></html>"

    parsed = parse_rfc822(
        build_eml(valid_scenario, email, html),
        provider_message_id="e08",
        folder="INBOX",
    )

    assert missing_facts(parsed.body, FACTS) == []
