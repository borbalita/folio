# 001/05 — Demo newsletters

## Goal
The demo user of [finance plan 003](../../../../05-finance/plans/003-finance-demo/README.md) gets AI News with two invented newsletters, so the News agent can be shown without real newsletters.

## Scope
- **Access:** AI News reads a news-specific mailbox set: all of the user's active mailboxes, demo included (like Finance's `invoice_mailbox_ids`). The News card, `require_agent_access("news")` and the tools follow it; Email keeps excluding the demo mailbox.
- **Sources:** two fictional newsletters, "The Daily Tensor" (`demo_tensor`) and "AI Detective" (`demo_detective`), added to the newsletter sources (check constraint) and to the coverage line's display names. Never TLDR or Alpha Signal names, in the newsletter names or in the item text.
- **Fixture (changed 2026-10-22 at the owner's request):** 37 items from the owner's real TLDR and Alpha Signal editions of 8–21 Oct, every title and blurb rephrased, never copied. TLDR items appear as The Daily Tensor, Alpha Signal items as AI Detective. It holds all five real big stories (Anthropic's Scion, Gemini 4 Argon, Muse Spark Open, OpenAI's legacy-code model, Claude's toxin binders) and, for the demo questions, security news (Cyber Verification Program and the eMudhra TLS certificates as big stories, plus Cisco, BeyondTrust, OpenCode, PHP, agent risks) and new models (Haiku 5.5, DeepSeek Flash, LiquidAI, Fish Audio, NVIDIA, GLM-Legal, Black Forest Labs, GPT-6). Links go to the original articles or the companies' newsrooms, never to newsletter tracking links. Day offsets keep the real spacing from 22 Oct. Items carry precomputed embeddings, made once by a small script and committed, so seeding makes no model calls.
- **Isolation (added 2026-10-22):** `news_stories` has no owner, so the story build (`rebuild_stories`, after every email ingest) groups only items from non-demo mailboxes, and the Telegram big-news summaries load only non-demo stories. Demo stories come only from the reset. A story is big when it holds both newsletters of one pair: TLDR + Alpha Signal, or The Daily Tensor + AI Detective.
- **Telegram for the video (added 2026-10-22):** a "Send news summary to Telegram" button on the presenter page (`/finance/demo`) builds the summary of the demo's big stories from the last 7 days, in the format of the real summaries, and sends it at once to the owner's usual chat (`TELEGRAM_CHAT_ID`), quiet hours or not. It is not recorded in the notifications table.
- **Seeding:** part of 003/03's base state and reset: the demo mailbox gets newsletter emails, items and stories (stories written directly, no grouping model), dated relative to today.

## Out of scope
- Real newsletters for the demo; web search.

## Acceptance criteria
- Given the demo user, when the agent list loads, then it has `news` and `finance` but not `email`. (test)
- Given the demo user, when a News tool runs, then it reads only the demo mailbox; given the owner, only the owner's. (test)
- Given a reset on two different days, then the newsletter dates move with today. (test)
- Given a reset, then some stories are big, some single-newsletter, and some span several days. (test)
- Given demo news items, when the story build runs after an email ingest, then it neither reads nor changes demo items or demo stories. (test)
- Given demo big stories, when the cron plans Telegram summaries, then none of them is included. (test)
- Given items from The Daily Tensor and AI Detective in one story, then the story is big; given TLDR and AI Detective, it is not. (test)
- Given the demo user on the presenter page, when they press "Send news summary to Telegram", then the owner's chat receives a summary of the demo's big stories within a minute. (manual)
- Given the demo user, when they ask "What were the big stories this week?", then invented big stories show with "both newsletters" coverage lines, and citations open. (browser)

## Dependencies
003/03 (base state and reset). The access change and the fixture can be done before it.

## Notes
- Implementation plan: [05-demo-newsletters.plan.md](05-demo-newsletters.plan.md).
- Decided 2026-10-21 in chat: fictional names, not real newsletters; "AI Detective" at the owner's request. Source keys stay neutral so a rename is one line.
- Precomputed embeddings depend on the embedding model and dimensions; changing either means rerunning the script.

## Verified

2026-10-22, branch `feat/news-demo` (fast suite: 855 passed; ruff, `tsc`, lint clean; integration tests against the local eval database pass). Built subagent-driven: six task reviews and one whole-branch review, whose three Important findings were fixed (display names in citations, real newsletter names in the prompt, read order in the story build).

- Demo user's agents: `documents`, `news`, `finance`, no `email`: `tests/api/test_news_access.py`; browser: the start page shows Finance, AI News, Document Copilot. Pass.
- News tools read only the demo mailbox for the demo user, only the owner's for the owner: `test_news_access.py`, news tool filter tests. Pass.
- Dates move with today: `tests/demo/test_demo_news_state.py`. Pass.
- Big, single-newsletter and multi-day stories after a reset: fixture and state tests (7 big, 3 multi-day). Pass.
- The story build never reads or changes demo items or stories: `test_rebuild_stories_never_touches_demo_stories`, `test_rebuild_stories_reads_stories_before_demo_story_ids`; reset integration test (fails with 29 orphaned stories when the story delete is removed). Pass.
- Telegram summaries skip demo stories: `test_big_stories_exclude_demo_mailboxes`. Pass.
- Pair rule for "big": `test_news_stories.py` parametrised cases. Pass.
- Browser, local build against the shared database (migration `01b8354147e4` applied by the owner), signed in as the demo user, after a reset: "What were the big stories this week?" lists three big stories (TLS certificates, scorpion binders, COBOL) with "both newsletters" coverage lines; citations read "AI Detective" and "The Daily Tensor" and open the original article. "Any security news in the last two weeks?" and "Which new models were announced recently?" answer from the demo items. Pass.
- Added at the owner's request on 2026-10-22: news are listed newest first (tool output sorted; briefings keep big stories on top, newest first within): `test_search_hits_are_listed_newest_first`, `test_stories_are_listed_big_first_then_newest_first`, `test_items_within_a_story_are_listed_newest_first`; browser: the security answer runs 21 → 20 → 13 → 9 Oct. Pass.
- Telegram button: **pending** — the owner presses it on the presenter page (manual).
- Privacy page: unchanged — invented demo news to the owner's existing chat; no new data, recipient or service.
- PR: see the branch's pull request.
