from datetime import UTC, datetime

import pytest

from app.database.models.email.message import EmailLabel, NewsletterSource
from ingest.email.labels import LabelDecision, label, label_message, newsletter_match
from ingest.email.parse import ParsedMessage


def _parsed(from_address: str = "person@example.com") -> ParsedMessage:
    return ParsedMessage(
        message_id="id@example.com",
        provider_message_id="1",
        folder="INBOX",
        subject="Hello",
        from_address=from_address,
        from_name="",
        to_addresses=["you@yahoo.com"],
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        body="Please see the note.",
        attachment_filenames=("invoice.pdf",),
    )


def test_domain_and_full_address_map_to_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ingest.email.labels.settings.ai_newsletter_domains",
        {
            "tldrnewsletter.com": "tldr",
            "news@alphasignal.ai": "alpha_signal",
        },
    )
    assert newsletter_match("TLDR <dan@tldrnewsletter.com>") == NewsletterSource.TLDR
    assert newsletter_match("news@alphasignal.ai") == NewsletterSource.ALPHA_SIGNAL
    assert newsletter_match("other@alphasignal.ai") is None


def test_ai_newsletter_skips_the_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ingest.email.labels.settings.ai_newsletter_domains",
        {"tldrnewsletter.com": "tldr"},
    )

    def fail(_prompt: str) -> str:
        raise AssertionError("classifier should not run")

    label, source = label_message(_parsed("a@tldrnewsletter.com"), classifier=fail)
    assert label is EmailLabel.AI_NEWSLETTER
    assert source is NewsletterSource.TLDR


@pytest.mark.parametrize(
    "raw",
    ["needs_reply", "promotional", "newsletter", "invoice", "other"],
)
def test_classifier_accepts_each_label(raw: str) -> None:
    assert label(_parsed(), classifier=lambda _prompt: raw) is EmailLabel(raw)


def test_jev_question_describes_each_label() -> None:
    options = {
        item["const"]: item["description"]
        for item in LabelDecision.model_json_schema()["properties"]["label"]["anyOf"]
    }
    assert set(options) == {
        "needs_reply",
        "promotional",
        "newsletter",
        "invoice",
        "other",
    }
    assert "sell" in options["promotional"]
    assert "AI digest" in options["newsletter"]


def test_invalid_label_retries_once_then_falls_back_to_other() -> None:
    calls = {"n": 0}

    def classifier(_prompt: str) -> str:
        calls["n"] += 1
        return "not-a-label"

    assert label(_parsed(), classifier=classifier) is EmailLabel.OTHER
    assert calls["n"] == 2
