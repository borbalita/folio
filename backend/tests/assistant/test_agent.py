from __future__ import annotations

from app.assistant.agent import LOOKING_THROUGH_FILINGS, looking_through_label


def test_looking_through_label_with_ticker() -> None:
    assert looking_through_label("AAPL") == "Looking through AAPL filings"
    assert looking_through_label("  AAPL  ") == "Looking through AAPL filings"


def test_looking_through_label_without_ticker() -> None:
    assert looking_through_label(None) == LOOKING_THROUGH_FILINGS
    assert looking_through_label("") == LOOKING_THROUGH_FILINGS
    assert looking_through_label("   ") == LOOKING_THROUGH_FILINGS
