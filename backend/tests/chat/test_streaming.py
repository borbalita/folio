from __future__ import annotations

import json

from app.chat.streaming import format_status_part


def test_format_status_part_is_transient() -> None:
    frame = format_status_part("Looking through AAPL filings")
    assert frame.startswith("data: ")
    payload = json.loads(frame[len("data: ") :].strip())
    assert payload == {
        "type": "data-status",
        "data": {"label": "Looking through AAPL filings"},
        "transient": True,
    }
