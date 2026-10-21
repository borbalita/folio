# 001/03 — News pages and picker card

## Goal
The owner opens AI News from the picker and chats in their own news threads.

## Scope
- Picker card "AI News": "Big AI stories and briefings from your newsletters, with citations".
- `/news` routes reusing the Email chat layout and news citations; empty state with "What were the big stories this week?" and "Catch me up since Monday".

## Acceptance criteria
- Given the owner, when the picker opens, then the AI News card shows and opens `/news`. (browser)
- Given "What were the big stories this week?", when answered, then only big stories show, ranked, each with its coverage line, and citations open the articles. (browser)
- Given "Catch me up since Monday", when answered, then big stories come first, then other stories grouped by theme, all from that period. (browser)

## Dependencies
001/02.

## Verified

2026-10-21, branch `feat/news-agent-chat`, PR [borbalita/folio#70](https://github.com/borbalita/folio/pull/70), local backend and frontend against the real database.

- Picker → AI News card shows ("Big AI stories and briefings from your newsletters, with citations.") and opens a `/news` thread. Pass.
- "What were the big stories this week?" → "this week" = Oct 19–21; the one big story (OpenAI legacy-code modernization) with "both newsletters · 2 items · Oct 20", citing both items; the TLDR source opens its article ("Open article"); the Alpha Signal item has no link, as most don't. Pass.
- "Catch me up since Monday" → the big story first with its reason, then 20 other stories in 5 themes, all from Oct 19–21 (re-run after the period fix). Pass.
- `pnpm tsc --noEmit` and `pnpm lint` clean.
- Note: the briefing is long (21 stories for 3 days); the cap question stays open in the spec.
