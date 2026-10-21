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
