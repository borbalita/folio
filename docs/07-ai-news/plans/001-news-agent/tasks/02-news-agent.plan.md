# 001/02 — News agent, tools and chat turn: implementation plan

Task: [02-news-agent.md](02-news-agent.md). Spec: [README](../README.md), Design.

**Goal:** a `news` chat agent that answers from the user's newsletters with three tools, cites items, and knows what "big" means.

**Architecture:** a new `app/news_assistant/` package mirroring `email_assistant/` (agent, deps, outputs, tools, instructions). The orchestrator gets `_NewsChatAgent`, a citing agent that stores citations as news items in `email_citations` (the table already holds `news_item_id`), with its own grounder wording. Access reuses the Email rule.

## Decisions within the design

- `NewsAgentDeps(user_id, thread_id, news, seen_ids, seen_passages, status_queue)` with `remember(item_id, passage)`, like the Email deps.
- Tools, all through `NewsSearchFilters` scoped to `mailboxes.active_mailbox_ids(user_id)`; no dates → `until = berlin_today()`, `since = until - 6 days`; one date only → only that bound:
  - `list_big_news(since?, until?)` → `stories(big_only=True, limit=settings.retrieval_top_k)`, empty text "No big stories in that period."
  - `catch_up(since?, until?)` → `stories(limit=CATCH_UP_LIMIT=60)`, big first by ranking; empty text "No newsletter stories in that period."
  - `search_news(query, since?, until?, big_only=False)` → `search`, as in Email (no default window: a topic search is not a briefing).
  - Each remembers every returned item; status label "Reading your AI newsletters".
- `berlin_today()` lives in `app/news_assistant/tools.py`; the Email tool keeps its own copy until 001/04 deletes it.
- `NewsAnswer(answer, citations: list[NewsCitationRef(chunk_id, citation_index, excerpt)], insufficient_evidence)`; `chunk_id` keeps the shared citing path.
- `NewsGrounder`: Email's rules, news wording ("…no cited newsletter items…").
- Agents: `agents_for` adds `news` with `email` (active mailbox); `require_agent_access("news")` = `require_email_access`; `AgentName` gains `news`.
- Migration `allow news chat threads`: drop and recreate `ck_chat_threads_agent` with `news`; model check updated.

## Tests (red first)

- `tests/news_assistant/test_news_tools.py`: default 7 days; one-date passthrough; `catch_up` limit 60 and not big-only; `list_big_news` big-only; items remembered, stories not; no mailbox → empty texts.
- `tests/news_assistant/test_news_turn.py` (scripted agent through `run_turn`, agent `news`): big news cites returned items, stored as `news_item_id`; citing the story id is refused with the News grounder's text; the prompt starts with today's date.
- `tests/news_assistant/test_instructions.py`: the instructions define big as both newsletters, forbid calling single-newsletter stories big, and name the three tools (the prompt is the product).
- `tests/api/test_email_access.py`: `/me` lists `news` with an active mailbox and not without; news routes 403 without a mailbox.
- `tests/database/test_chat_thread_agents.py`: the model check and the newest migration both allow `news`.

## Check

`uv run pytest -m "not integration"`, `uv run ruff check .`, `alembic upgrade head` (owner's OK), then a real question through the API with a local server once 001/03 has the page; the browser criteria live in 001/03.
