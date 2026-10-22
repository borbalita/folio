# 001 — AI News agent: big stories and briefings

- Created: 2026-10-20
- Status: In progress
- Current stage: 001/01–04 done; 001/05 (demo newsletters) added, waits for finance 003/03

## Approval state

- 2026-10-20: in chat, the owner asked for a chatbot only about AI news that knows what big or important news means. They chose: a focused place for news, judged importance, briefings, demo-friendly; importance by coverage only; briefings on request in chat; owner-only; news moves out of the Email agent. Approach 1 (rank by coverage, grouping unchanged) chosen over grouping same-newsletter items across days. Design sections 1–3 approved. No evals for this agent.
- 2026-10-20: the owner approved the written spec and asked to build it; the plan is Ready.
- 2026-10-22: added to 001/05 at the owner's OK, after planning found stories are global: the story build and the Telegram summaries skip demo items; "big" means both newsletters of one pair (TLDR + Alpha Signal, or the two demo newsletters); the presenter page gets a button that sends a news summary of the demo's big stories to the owner's usual Telegram chat, for the demo video.
- 2026-10-21: the owner approved 001/05, demo newsletters for the finance demo user: two fictional newsletters ("The Daily Tensor", "AI Detective"), AI News reads the demo mailbox, seeded by 003's reset with precomputed embeddings.
- 2026-10-21: final review: stories count only items inside the period, so big means both newsletters within it (owner's spec says "all from that period").
- 2026-10-20: demo data comes from a separate plan; this agent must work for a demo account's own invented newsletters.

## Problem

AI newsletter items are stored and grouped into stories, but questions about them go to the Email agent, mixed with mail. The owner wants one place to ask "what were the big stories this week?" or "catch me up since Monday", with the important stories first and a clear, consistent meaning of "big". It should also be something the owner can show in demos.

## Current system

- **Newsletters:** ingest labels TLDR and Alpha Signal editions `ai_newsletter`, extracts their items ([news.py](../../../../backend/ingest/email/news.py)) and rebuilds `news_stories` on every run ([stories.py](../../../../backend/ingest/email/stories.py)). Items from the same newsletter are never grouped. A story is big when both newsletters cover it (`is_big`). Story ids are not stable across runs.
- **Answers:** the Email agent has `search_news` and `list_big_news` ([tools/news.py](../../../../backend/app/email_assistant/tools/news.py)) on the news retriever ([retrieval/news](../../../../backend/app/retrieval/news/)), and cites news items through the email citation path.
- **Agents:** `chat_threads.agent` is checked to `documents`, `email`, `finance`; the orchestrator dispatches per agent ([orchestrator.py](../../../../backend/app/chat/orchestrator.py)); the picker reads [agents.ts](../../../../frontend/src/lib/agents.ts). Email is shown to users with an active mailbox ([email_access.py](../../../../backend/app/auth/email_access.py)).
- **Notifications:** [06-notifications 001](../../../06-notifications/plans/001-telegram/README.md) sends big stories to Telegram using the same `is_big`.
- **Evals:** the Email agent's eval cases contain no AI-news questions; two eval modes pass a news retriever to its deps. The news extraction benchmark (eval plan 003) covers ingest, not agents.

## Goals and non-goals

Goals:

- A News agent with its own picker card and threads that answers AI-news questions from the user's own newsletters, citing items.
- "Big" means one thing everywhere: covered by both newsletters. The agent says why a story is big.
- "Catch me up" briefings: big stories first, then the rest grouped by theme.
- The Email agent answers about mail only.

Non-goals: model-rated importance or interest lists; grouping same-newsletter items across days; pushed or scheduled briefings (06-notifications); a briefing page; evals for this agent; demo data (its own plan).

## Decisions

- **Importance is coverage only.** Big = `is_big` (both newsletters). Stories are ranked by coverage. Rejected: lead position, model-judged event type, the owner's interests.
- **Rank by coverage, grouping unchanged.** Rejected for now: pairing same-newsletter items from different days so a recurring story can be big; it changes ingest and needs a check on real data. Revisit if recurring single-newsletter stories matter.
- **Briefings on request in chat.** Rejected: a briefing page; pushed briefings belong to notifications.
- **Owner-only, per user's mailbox.** The agent reads only the signed-in user's newsletters, so a demo account sees its own invented news. Rejected: news for every signed-in user.
- **News leaves the Email agent.** Rejected: both agents answering news.
- **No evals for this agent** (owner's choice).

## Design

```text
picker card "AI News"  ─►  /news  (threads, like /email)
                               │
chat orchestrator ── agent "news" ──► PydanticAI agent (app/news_assistant/)
                                         ├─ tools: list_big_news, catch_up, search_news
                                         └─ instructions: what "big" means, ranking, citing
                                                  │
                     news retrieval (news_items, news_stories) + coverage computed on read
```

- **Coverage per story,** computed on read, nothing stored: `sources` (newsletters, 1 or 2), `items`, `days` (first to last appearance). Ranking: big first, then sources, items, days, newest. Each story carries a coverage line, e.g. "both newsletters · 3 items · Oct 12–14".
- **Tools** (scoped to the user's mailboxes; no dates means the last 7 days, resolved from the date that starts each question):
  - `list_big_news(since?, until?)`: big stories in the period, ranked, with coverage line, title, blurb, links and citable item ids.
  - `catch_up(since?, until?)`: big stories first, then other stories ranked, at most 60.
  - `search_news(query, since?, until?, big_only?)`: topic search, as today.
- **Instructions:** big is defined in one sentence; only stories the tools mark big are called big, and the coverage line says why; a single-newsletter story that recurs is "recurring", never "big"; briefings are short: big stories first, then a few themes; answers come only from tool results, cite items, never stories; an empty period is said plainly.
- **Chat:** an orchestrator turn type `news` reusing the news-item citation path and grounding of the Email agent. Migration: add `news` to `ck_chat_threads_agent` (hand-written; autogenerate misses check changes).
- **Access:** the News card and `/news` routes for users with an active mailbox, like Email; threads are per user.
- **Email agent:** loses `search_news` and `list_big_news` and its news deps; its instructions answer AI-news questions with a one-line pointer to the News agent, without searching or citing. Picker description: "Search your mail, with citations to each message." Old threads with news citations still render. The two eval modes stop passing a news retriever.
- **Frontend:** picker card "AI News" ("Big AI stories and briefings from your newsletters, with citations"); `/news` reuses the Email chat layout and news citations; empty state suggests "What were the big stories this week?" and "Catch me up since Monday".
- **Failure modes:** no newsletters in the period → the agent says so; grounding rejects a citation no tool returned, as for Email.
- **Privacy:** tracing stays content-free (eval plan 004); no new data leaves the app.
- **Dependencies:** none new.

## Success criteria

1. "What were the big stories this week?" lists only big stories, ranked, each with its coverage line, citing items that open their articles.
2. "Catch me up since Monday" gives big stories first, then other stories grouped by theme, all from that period.
3. A news question to the Email agent gets a pointer to the News agent and no news search.
4. A user without an active mailbox sees no News card and gets 403 on news routes; nobody sees another user's news.
5. A demo account with invented newsletters gets the same behaviour from its own data.

## Tasks

- [x] [001/01 — Story coverage and ranking](tasks/01-coverage.md)
- [x] [001/02 — News agent, tools and chat turn](tasks/02-news-agent.md) — after 01
- [x] [001/03 — News pages and picker card](tasks/03-news-pages.md) — after 02
- [x] [001/04 — News moves out of the Email agent](tasks/04-email-without-news.md) — after 02
- [ ] [001/05 — Demo newsletters](tasks/05-demo-newsletters.md) — after finance 003/03

## Open questions and risks

- **Recurring single-newsletter stories** are never big. Next action: watch real briefings; if it matters, a follow-up plan pairs same-newsletter items across days with a check on real data.
- **Briefing size:** in the 001/03 run, three days gave 21 stories; long but readable. Next action: watch real use; lower the cap or ask for fewer themes if briefings feel long.
- **Demo data:** finance 003/01 keeps the demo mailbox out of `active_mailbox_ids`, so AI News needs its own mailbox rule for the demo user. Next action: [001/05](tasks/05-demo-newsletters.md); success criterion 5 is checked there.
- **Web search for story details** (asked 2026-10-21, not now): OpenAI's built-in web search via PydanticAI's `WebSearchTool`; needs web pages as a second citation kind (grounding, storage, source panel) and a rule to search only for details on a story. About 2 days.
