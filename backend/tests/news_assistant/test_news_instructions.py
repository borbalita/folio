from app.news_assistant.agent import INSTRUCTIONS_PATH, get_agent, news_prompt


def test_instructions_define_big_and_name_the_tools() -> None:
    text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    assert "both newsletters" in text
    assert "recurring" in text
    for tool in ("list_big_news", "catch_up", "search_news"):
        assert tool in text


def test_agent_has_exactly_the_three_news_tools() -> None:
    names = set(get_agent()._function_toolset.tools)

    assert names == {"list_big_news", "catch_up", "search_news"}


def test_prompt_starts_with_todays_date() -> None:
    from datetime import date

    prompt = news_prompt("Catch me up", today=date(2026, 10, 21))

    assert prompt.startswith("Today is 2026-10-21 in Europe/Berlin.")
    assert prompt.endswith("Catch me up")
