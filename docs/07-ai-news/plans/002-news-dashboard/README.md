# 002 — AI News dashboard, explanations and security alerts

- Created: 2026-11-05
- Status: In progress
- Current stage: 002/01–04 implemented with PRs open, each with browser and manual checks still to do; 002/05 unblocked by the 2026-11-06 live check and owner's decision

## Approval state

- 2026-11-05: in chat, the owner asked for a dashboard of AI news by date, notifications about security news, Telegram messages with a simple explanation, and chat about the news. They chose: a short explainer as the message form; AI security plus major incidents as the alert scope; all stories on the dashboard with filters; a Chat button that opens a new thread, reads the newsletter text and can search the web; one alert per incident plus real updates; the stored newsletter as the source of fuller text; one classification call per ingest run.
- 2026-11-05: the owner approved the written spec and tasks as written, including quiet hours for security alerts and web search in every news thread; the plan is Ready.
- 2026-11-05: the owner's preference on length, relayed from their main session ("i just want something long enough to understand"), replaces the 3–5 sentence limit.
- 2026-11-06: after the live check in 002/05, the owner chose how web citations are grounded: a URL counts if it was a search result or a page the model opened in this turn; a citation matching neither is removed and the answer kept; URLs compare ignoring query string, fragment, scheme, a leading `www.`, host case and a trailing slash. This replaces "its URL must come from this turn's search results".

## Problem

AI News can only be reached by asking. There is no place to scan what came in, day by day. Telegram sends only big stories, so nearly all security news never arrives: in the last 15 days the newsletters carried about 15 real incidents (rough hand count) and one was big. The messages that do arrive restate facts without saying what they mean, and the owner finds some of them too thin.

## Current system

- **Stories:** ingest extracts each newsletter's items into `news_items` and rebuilds `news_stories` on every run ([news.py](../../../../backend/ingest/email/news.py), [stories.py](../../../../backend/ingest/email/stories.py)). About 33 stories per weekday. In the last 30 days 16 of 611 were big. Story ids are not stable, and item ids change when an email is re-embedded; an item's email and position survive both.
- **Why messages are thin (checked on real data, 2026-11-05):** all 12 real news messages carry a model summary and none used the fallback, so failed calls aren't the cause. The summary is written from titles and one-sentence blurbs ([summary.py](../../../../backend/app/notifications/summary.py)), and its prompt asks for 2–3 short sentences of restated facts. The stored `emails.body` has far more: TLDR gives a paragraph per story and Alpha Signal's lead stories have long plain-language explainers. Some Alpha Signal blurbs are empty, and 371 of its 377 items have no link.
- **Notifications:** the outbox in `notifications` is filled and sent at the end of each ingest run ([06-notifications overview](../../../06-notifications/overview.md)). Keys `news:<email id>:<position>` make a story announce once.
- **Chat:** `/news` has threads and its own agent ([news_assistant](../../../../backend/app/news_assistant/)), which sees only titles and blurbs and answers only from them. It runs on the Responses API ([chat_model.py](../../../../backend/app/chat_model.py)).
- **Repeats:** an incident runs for days and across items the story grouping doesn't join, because same-newsletter items are never paired. PHP2Shell appeared in at least 7 items from 22 to 28 Oct.
- **Demo:** demo mailboxes are skipped by the story build and by Telegram; a demo account reads its own invented newsletters. The presenter's button sends a demo story through `summary.news_text` ([news_telegram.py](../../../../backend/app/demo/news_telegram.py)).

## Goals and non-goals

Goals:

- A dashboard at `/news`: every story by day, newest first, with Big and Security badges and filters.
- Telegram news messages that explain a story in plain words, readable without opening a link.
- Telegram alerts for security stories, one per incident plus real updates.
- A Chat button on each story that opens a thread about it, where the agent can read the newsletter text and search the web.

Non-goals: new news sources; explanations for stories that send no message; explanations for stories announced before this plan; pairing same-newsletter items into one story; fetching linked articles at ingest; buttons or commands in Telegram; a daily digest; interest lists or any other topic alerts; evals for the agent.

## Decisions

These reverse earlier decisions, by the owner's choice on 2026-11-05:

- **A news page exists.** [Plan 001](../001-news-agent/README.md) rejected a briefing page. The dashboard is a dated list rather than a written briefing, but it is the page that plan left out; briefings stay in chat.
- **The model judges one topic: security.** [Notifications plan 001](../../../06-notifications/plans/001-telegram/README.md) rejected topic lists and model-rated importance, and plan 001 rejected a model-judged event type. Security alerts need this because coverage can't find them. It is limited to security. "Big" still means both newsletters and nothing else, and Security is a separate mark, not a rank.
- **Telegram messages may go beyond restating.** The summary prompt forbade opinions and added details. An explanation may define terms in plain words and say why a story matters, but facts about the event still come only from the newsletters.
- **The News agent may leave the newsletters.** Plan 001 answers only from tool results, and listed web search as "not now". Web search is now in, with its own citation kind.

Other decisions:

- **Explanation form:** a headline, then plain sentences long enough to understand the story without opening the links: what happened, terms explained, why it matters. No fixed sentence count, and not a long briefing. Rejected: labelled sections (rigid, padded for small stories); same length with more facts (still says nothing about meaning).
- **Fuller text comes from the stored newsletter.** An explanation or a chat reads the whole `emails.body` of each item's edition, with the story named as the focus. It needs no schema or extraction change and works on all history. Rejected: a `details` field from extraction (migration, benchmark rerun, and re-extraction could shift the positions that Telegram keys rely on); fetching linked articles (Alpha Signal has almost no links).
- **Alert scope: AI security plus major incidents.** Qualifies: AI as target, tool or cause of harm (sandbox escapes, malicious AI tooling, model misuse, critical flaws found by AI); active exploitation; critical flaws in widely used software; large breaches or hacks. Doesn't qualify: advice and opinion pieces, security products and partnerships, bug bounty programmes, routine patches, stories that only mention security. Expect about one alert a day. Rejected: AI only (misses the GitLab flaw and the Binance hack); anything security-related (noisy).
- **One classification call per ingest run.** Rejected: keywords first (miss stories such as a model escaping its sandbox, and the saving is tiny); one call per story (about 33 a day, and harder to compare items within a batch).
- **Repeats:** one alert per incident, plus a follow-up when something materially changed. The same call decides, by comparing with the last 7 days of alerts. It may occasionally miss or repeat one, which is accepted. Rejected: strictly one (would hide that a flaw is now under attack); one per story (PHP2Shell would have sent several).
- **Dashboard shows everything,** filterable. Stories with a Telegram message also show their explanation. Rejected: only big and security (hides the other 30 stories a day); explanations for all (about 33 more calls a weekday, and most stories don't need one).
- **Web search is off for demo accounts.** Their stories are invented, so the web would contradict them or find nothing.
- **Web citations are removed, not refused (owner, 2026-11-06).** A web citation counts if its URL was a search result or a page the model opened in this turn; the live check showed a correct citation to an opened page that the search sources didn't list. One matching neither is removed and the answer is kept, because the rest of the answer can still stand. URLs compare ignoring query string, fragment, scheme, a leading `www.`, host case and a trailing slash, because sources carry tracking parameters. Newsletter item citations keep their strict grounding. Rejected: search results only (rejects correct answers); failing the turn (loses a good answer over one bad link).
- **Quiet hours apply to security alerts,** 22:00–07:00 like every other message. Newsletters arrive in the morning, and an AI newsletter's story isn't an emergency that needs waking up for.

## Design

```text
email ingest run
  extract items → rebuild stories → notify step
                                      ├─ classify new items (one call) ──► news_item_notes
                                      ├─ plan: big stories + new security alerts
                                      ├─ explain each pending story from its newsletters ──► news_item_notes
                                      └─ send via Telegram

/news ── dashboard (GET /news/stories) ── Chat button ──► new thread with story_items
                                                              │
                                 News agent: existing tools + read_story + web search
```

- **`news_item_notes`** (added in 002/02): one row per newsletter item, keyed by `(email_id, position)` like the notification keys, so it survives re-embedding and story rebuilds. Columns: `headline`, `explanation` (from the message's model call), `security` (bool, null until classified), `alert_status` (`new`, `update`, `repeat`, null). RLS on, cascade from `emails`.
- **Explanations:** `summary.py` reads each item's edition text and writes `{headline, explanation}`. The prompt names the story's titles and tells the model to ignore the other stories in the newsletter; links stay outside the model, as today. A failed call sends the first headline, its blurb when there is one, and the links, and stores no explanation.
- **Dashboard API:** `GET /news/stories?before=<date>&days=14&only=big|security`, behind the `news` agent check and scoped to the user's news mailboxes. A story appears once, on its newest day, with all the user's items. Within a day: big, then security, then newsletter order. Each story has a title (the stored headline or its first item's title), a blurb (the longest non-empty one), badges, links per newsletter, item refs and an explanation when there is one.
- **Dashboard page:** the `/news` index route renders it in place of `ChatEmptyState`, beside the existing thread sidebar. Days as sections, All/Big/Security filters, and "Load older". Newsletters without a link show none. The picker's description and the empty hints change to match.
- **Chat from a story:** `chat_threads` gains nullable `story_items`, a list of `{email_id, position}`. The button creates a thread with those and the story's title, opens it, and sends "Explain this story" as the first message. Each turn's prompt names the story and its current item ids. A new tool `read_story(item_id)`, available in every news thread, returns the edition text with the story named, scoped to the user's mailboxes; citations stay on items.
- **Classification:** in the notify step, items from the last 2 days without a classification, non-demo, go to one structured call with their titles and blurbs and the last 7 days of alert headlines. For each item it returns `security` and, when true, `new`, `update` or `repeat`; it marks repeats within the batch too. Answers with unknown indices are dropped. A failed call logs its type and retries next run; big-story messages still go out.
- **Security messages:** a new notification kind `news_security`. A story with a `new` or `update` item in the 2-day lookback is sent `🔒 <headline>`, or `🔒 Update: <headline>`, with the explanation, which also says who is affected and what to do when the newsletter does. It uses the same `news:<email>:<position>` keys, so a big security story sends one message and the Big path doesn't announce it again.
- **Backfill:** `python -m ingest.news_security --days 30` classifies older items for the dashboard's badges. It writes `security` only, with `alert_status` null, so it never sends anything.
- **Web search:** PydanticAI's `WebSearchTool` on the News agent for non-demo users. The instructions say to search only for details the newsletters lack about a story or topic, and to say which part came from the web. A web citation is a second citation kind in storage, grounding and the source panel. Its URL must be a search result or a page the model opened in this turn, compared by the rule in Decisions; otherwise that citation is removed and the answer kept. Sources have no titles, so the panel's title comes from the model's citation. Raw citation markers in the model's text are stripped before it is stored or shown.
- **Failure modes:** no newsletters that day means no section; an empty filter says so; a newsletter body too large for a call isn't expected at about 10k characters. A web page can carry injected text, but the agent's other tools are read-only and scoped to the user's news, and it can send nothing.
- **Demo accounts:** the dashboard and chat work from their own items. They never get classified or get notes, so they show Big but no Security badges or explanations. The presenter's Telegram button keeps working and gets the new explanation form.
- **Tracing:** stays content-free. The explanation and classification calls, like extraction, use the OpenAI SDK directly and aren't traced.
- **Privacy page:** 002/01 changes the Telegram line from headlines to headlines and explanations. 002/04 adds security alerts. 002/05 adds that news questions may go to OpenAI's web search. Each updates "Last updated". 002/02 and 002/03 change nothing the page describes.
- **Dependencies:** none new.

## Success criteria

1. A new big story's Telegram message explains in plain words what happened and why it matters, and can be understood without opening a link.
2. `/news` lists every story by day, newest first, and filters to Big and to Security.
3. The Chat button opens a thread about that story, and the first answer draws on the newsletter text, with citations that open.
4. A question the newsletters can't answer gets a web-sourced answer with a working web citation, marked as coming from the web.
5. A new security story in scope sends one alert. Later items about the same incident send nothing unless something materially changed.
6. Over the last 30 days of real newsletters, the owner agrees with what the classifier marks as security.
7. A demo account's dashboard and chat work from its own data, without web search, and nothing of its reaches the owner's Telegram except the presenter's button.

## Tasks

- [ ] [002/01 — Telegram explanations](tasks/01-telegram-explanations.md)
- [ ] [002/02 — News dashboard](tasks/02-dashboard.md) — after 01
- [ ] [002/03 — Chat from a story](tasks/03-chat-from-story.md) — after 02
- [ ] [002/04 — Security alerts](tasks/04-security-alerts.md) — after 02
- [ ] [002/05 — Web search in the News agent](tasks/05-web-search.md) — after 03

## Open questions and risks

- **Classifier quality:** the alert scope is a judgment call and there is no labelled set. Next action: the owner reviews the 30-day backfill in 002/04 before alerts go on, and the rubric is adjusted there.
- **Alert volume:** about one a day is an estimate from a hand count. Next action: watch the first two weeks; narrow the rubric if it's too many.
- **Neighbouring stories in explanations:** the model reads a whole newsletter and could mix in another story. Next action: check real messages in 002/01; if it happens, cut the text down to the story's passage.
- **Web sources with structured output:** resolved by the live checks of 2026-11-05 and 2026-11-06 in [002/05](tasks/05-web-search.md): the sources and opened pages arrive in the same run's messages as `NewsAnswer`, and grounding follows the owner's rule in Decisions. Each web turn used about 21k–38k input tokens, so the instructions keep searching to when the newsletters lack the detail.
- **Explanations only when Telegram is on:** they are written for pending messages, so a local run with Telegram off shows none on the dashboard. Accepted.
