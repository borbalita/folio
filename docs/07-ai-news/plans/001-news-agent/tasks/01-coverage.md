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
