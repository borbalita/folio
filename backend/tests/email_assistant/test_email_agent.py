from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.email_assistant import agent
from app.email_assistant.agent import email_prompt


def test_prompt_states_the_given_reference_date() -> None:
    prompt = email_prompt("Which invoices came last week?", today=date(2026, 10, 1))

    assert prompt.startswith(f"Today is 2026-10-01 in {settings.email_timezone}.")
    assert prompt.endswith("Which invoices came last week?")


def test_prompt_defaults_to_today_in_the_configured_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[ZoneInfo] = []

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: ZoneInfo | None = None) -> FixedDatetime:  # type: ignore[override]
            assert tz is not None
            seen.append(tz)
            return cls(2026, 3, 15, 23, 30, tzinfo=tz)

    monkeypatch.setattr(agent, "datetime", FixedDatetime)

    prompt = email_prompt("Anything new?")

    assert prompt.startswith(f"Today is 2026-03-15 in {settings.email_timezone}.")
    assert seen == [ZoneInfo(settings.email_timezone)]


def test_email_agent_only_searches_mail() -> None:
    from app.email_assistant.agent import get_agent

    assert set(get_agent()._function_toolset.tools) == {"search_emails"}


def test_instructions_point_news_questions_to_the_news_assistant() -> None:
    from app.email_assistant.agent import INSTRUCTIONS_PATH

    text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    assert "AI News assistant" in text
    assert "insufficient_evidence" in text
    assert "list_big_news" not in text
    assert "search_news" not in text
