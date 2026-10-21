# 001/05 — Demo newsletters

## Goal
The demo user of [finance plan 003](../../../../05-finance/plans/003-finance-demo/README.md) gets AI News with two invented newsletters, so the News agent can be shown without real newsletters.

## Scope
- **Access:** AI News reads a news-specific mailbox set: all of the user's active mailboxes, demo included (like Finance's `invoice_mailbox_ids`). The News card, `require_agent_access("news")` and the tools follow it; Email keeps excluding the demo mailbox.
- **Sources:** two fictional newsletters, "The Daily Tensor" (`demo_tensor`) and "AI Detective" (`demo_detective`), added to the newsletter sources (check constraint) and to the coverage line's display names. Never TLDR or Alpha Signal names.
- **Fixture:** about two weeks of invented items (labs, models, products; links on `example.com`), with day offsets from today: stories in both newsletters, stories in one, and some over several days. Items carry precomputed embeddings, made once by a small script and committed, so seeding makes no model calls.
- **Seeding:** part of 003/03's base state and reset: the demo mailbox gets newsletter emails, items and stories (stories written directly, no grouping model), dated relative to today.

## Out of scope
- Real newsletters for the demo; web search.

## Acceptance criteria
- Given the demo user, when the agent list loads, then it has `news` and `finance` but not `email`. (test)
- Given the demo user, when a News tool runs, then it reads only the demo mailbox; given the owner, only the owner's. (test)
- Given a reset on two different days, then the newsletter dates move with today. (test)
- Given a reset, then some stories are big, some single-newsletter, and some span several days. (test)
- Given the demo user, when they ask "What were the big stories this week?", then invented big stories show with "both newsletters" coverage lines, and citations open. (browser)

## Dependencies
003/03 (base state and reset). The access change and the fixture can be done before it.

## Notes
- Decided 2026-10-21 in chat: fictional names, not real newsletters; "AI Detective" at the owner's request. Source keys stay neutral so a rename is one line.
- Precomputed embeddings depend on the embedding model and dimensions; changing either means rerunning the script.
