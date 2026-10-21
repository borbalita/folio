# 001/02 — News agent, tools and chat turn

## Goal
A `news` agent answers AI-news questions in its own threads from the user's newsletters, citing items, and knows what "big" means.

## Scope
- `app/news_assistant/`: agent, deps, instructions, tools `list_big_news`, `catch_up` (big first, then others, at most 60), `search_news`; no dates means the last 7 days.
- Instructions: the one-sentence definition of big, coverage lines as the reason, "recurring" never "big", short briefings, cite items only, say plainly when a period is empty.
- Orchestrator turn type `news` with the news-item citation path and grounding; `news` added to `ck_chat_threads_agent` (hand-written migration).
- Access: `news` among a user's agents when they have an active mailbox; threads per user.

## Out of scope
- Pages (001/03); removing news from Email (001/04).

## Acceptance criteria
- Given no dates, when a tool runs, then it covers the 7 days up to the question's date. (test)
- Given a scripted model asking for big news, when the turn runs, then it calls `list_big_news` and its answer cites only returned items. (test)
- Given an answer citing an item no tool returned, when the turn ends, then grounding rejects it. (test)
- Given a user without an active mailbox, when they open news threads or the agent list, then they get 403 and no `news`. (test)
- Given a `news` thread, when it is created, then the migration allows it. (test)

## Dependencies
001/01.

## Notes
- Implementation plan: [02-news-agent.plan.md](02-news-agent.plan.md).

## Verified

2026-10-21, branch `feat/news-agent-chat`, PR [borbalita/folio#70](https://github.com/borbalita/folio/pull/70).

- No dates → the 7 days up to the question's date: `test_no_dates_cover_the_seven_days_up_to_today` (both tools). Pass.
- Scripted big-news turn → `list_big_news`, answer cites only returned items, stored as `news_item_id`: `test_big_news_cites_the_returned_items_as_news`. Pass.
- Citing an id no tool returned (the story id) → rejected with the News grounder's wording: `test_citing_the_story_id_is_refused_with_news_wording`. Pass.
- No active mailbox → 403 on list, create and stream; `/me` without `news`: `test_news_routes_are_forbidden_without_a_mailbox`, `test_me_lists_documents_only_without_a_mailbox`. Pass.
- `news` threads allowed: `test_model_allows_news_threads`, `test_a_migration_allows_news_threads`; migration `2938db925e7d` applied (owner's OK) and a `news` thread created in the browser. Pass.
- Also: instructions define big and name the three tools; an empty period is answered as insufficient evidence and shown (`test_an_empty_period_answer_is_shown`, from the final review).
- Suite: `uv run pytest -m "not integration"`: 701 passed; `ruff check` clean.
