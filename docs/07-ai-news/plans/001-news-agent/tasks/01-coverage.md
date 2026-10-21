# 001/01 — Story coverage and ranking

## Goal
Stories read from the newsletters carry their coverage and come back ranked: big first, then by sources, items, days, newest.

## Scope
- A `Story` with `is_big`, its items, and coverage (`sources`, `items`, `days`) computed on read; nothing stored.
- `NewsRetriever.stories(filters, limit)`: stories in the period, scoped to the user's mailboxes, ranked, at most `limit`; `big_only` restricts to big ones.
- A coverage line per story, e.g. "both newsletters · 3 items · Oct 12–14" or "TLDR only · 1 item · Oct 12".
- The Email agent's `list_big_news` uses it until 001/04 removes it.

## Out of scope
- The News agent and its tools (001/02).

## Acceptance criteria
- Given a big story and single-newsletter stories with more items or days, when stories are ranked, then the big story comes first and the rest order by sources, items, days, newest. (test)
- Given `big_only`, when stories are read, then only big stories come back. (test)
- Given more stories than the limit, when stories are read, then the top-ranked ones are returned, not the newest. (test)
- Given stories over one day, several days and two months, when formatted, then each shows its coverage line with the right newsletters, item count and dates. (test)
- Given no active mailbox, when stories are read, then no query runs and nothing is returned. (test)

## Dependencies
None.

## Notes
- Implementation plan: [01-coverage.plan.md](01-coverage.plan.md).

## Verified

2026-10-20, branch `feat/news-agent`, PR [borbalita/folio#66](https://github.com/borbalita/folio/pull/66).

- Big story vs single-newsletter stories with more items or days → big first, then sources, items, days, newest: `test_rank_puts_big_first_then_sources_items_days_newest`, ties `test_rank_breaks_full_ties_by_story_id`. Pass.
- `big_only` → only big stories: `test_stories_big_only_and_dates_go_into_the_aggregate_query` (big = more than one newsletter among the user's own items). Pass.
- More stories than the limit → top-ranked kept, not the newest: `test_stories_keeps_the_top_ranked_not_the_newest`. Pass.
- Coverage lines over one day, several days, two months, and an unknown newsletter: `test_coverage_line` (4 cases), `test_format_marks_big_stories_and_lists_every_item_id`. Pass.
- No active mailbox → no query: `test_stories_with_no_mailbox_runs_no_query`. Pass.
- Also, from the final review: big and dates come only from the user's own items (`test_big_and_dates_come_from_the_users_own_items_only`); the Email agent's `list_big_news` without dates covers the last 7 days (`test_list_big_news_without_dates_covers_the_last_seven_days`).
- Both queries run read-only against the real database: for Oct 13–19, 3 big stories ("both newsletters · 3 items · Oct 14–15" first), then single-newsletter ones.
- Suite: `uv run pytest -m "not integration"` (no Langfuse keys, `EMAIL_RERANK=false`): 681 passed; `ruff check` clean.

