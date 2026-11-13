import pytest

from app.news_assistant.agent import INSTRUCTIONS_PATH, get_agent, news_prompt


def test_instructions_define_big_and_name_the_tools() -> None:
    text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    assert "both newsletters" in text
    assert "recurring" in text
    for tool in ("list_big_news", "catch_up", "search_news"):
        assert tool in text


def test_instructions_send_deep_questions_to_read_story_and_keep_stories_apart() -> None:
    text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    assert "read_story" in text
    assert "Never present another story in the same newsletter as this one" in text


@pytest.mark.parametrize("web_search", [True, False])
def test_agent_has_exactly_the_four_news_tools(web_search: bool) -> None:
    names = set(get_agent(web_search=web_search)._function_toolset.tools)

    assert names == {"list_big_news", "catch_up", "search_news", "read_story"}


def test_prompt_starts_with_todays_date() -> None:
    from datetime import date

    prompt = news_prompt("Catch me up", today=date(2026, 10, 21))

    assert prompt.startswith("Today is 2026-10-21 in Europe/Berlin.")
    assert prompt.endswith("Catch me up")


def test_an_empty_period_is_answered_as_insufficient_evidence() -> None:
    text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    sentence = text[text.index("If a period has no stories") :].split(". ", 1)[0]
    assert "insufficient_evidence" in sentence


def test_every_listed_item_is_read_before_it_is_cited() -> None:
    text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    assert "cite only items whose edition you read with read_story" in text
    assert "for each listed id" in text
