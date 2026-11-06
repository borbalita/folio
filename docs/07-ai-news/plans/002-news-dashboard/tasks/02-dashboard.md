# 002/02 — News dashboard

## Goal
The owner opens `/news` and scans every story by day, newest first, with big stories marked and explanations where a message was sent.

## Scope
- `news_item_notes` table keyed by `(email_id, position)`: `headline`, `explanation`, `security`, `alert_status`. RLS on, listed in `RLS_TABLES`, cascades from `emails`.
- The notify step stores the headline and explanation of each message it writes.
- `GET /news/stories?before=<date>&days=14&only=big`, behind the `news` agent check, scoped to the user's news mailboxes. A story appears once, on its newest day, with all the user's items. Within a day: big first, then newsletter order. Each story has a title (stored headline or first item's title), a blurb (longest non-empty), badges, links per newsletter, item refs, and its explanation when there is one.
- The `/news` index route renders the dashboard in place of `ChatEmptyState`, beside the thread sidebar: day sections, All/Big filters, expandable explanation, links, "Load older". New chat stays where it is.
- Picker description and hints in `agents.ts` mention the dashboard.

## Out of scope
- The Chat button (002/03); the Security badge and filter (002/04).

## Acceptance criteria
- Given a story with items on two days, when the list is built, then it appears once, on the newer day. (test)
- Given a window boundary inside a story's days, when two pages are loaded, then the story appears on one page only. (test)
- Given `only=big`, when the list is built, then only stories both newsletters cover are returned. (test)
- Given a story with an empty blurb on one item, when the list is built, then the non-empty blurb is shown. (test)
- Given a message written for a story, when the story is re-embedded and rebuilt, then its explanation still shows. (test)
- Given a user without an active mailbox, when they call the endpoint, then they get 403; given another user's items, they never appear. (test)
- Given the new table, when the migration tests run, then RLS is enabled on it. (test)
- Given the owner, when they open AI News from the picker, then days show newest first, Big filters, a story with a message expands to its explanation, links open, and "Load older" adds earlier days. (browser)
- Given a demo account, when it opens `/news`, then it sees its own invented stories with Big badges and no explanations. (browser)

## Dependencies
002/01.

## Notes
- Implementation plan: [02-dashboard.plan.md](02-dashboard.plan.md).

## Decisions made
- The response is `{days: [{date, stories}], nextBefore}`, camelCase like the other routes. `before` is exclusive and defaults to tomorrow in Berlin; the page holds the `days` days before it. `nextBefore` is the window start when the user has older items, else null; "Load older" passes it as `before`.
- A story belongs to the page where its newest day (among the user's items) falls. The loader reads every item of each story that touches the window, and `build_days` drops stories whose newest day is later, so a story crossing a boundary shows on the newer page only.
- `only=big` uses the story's `is_big` flag, as everywhere else. `only` accepts `big` only; `security` is a 422 until 002/04.
- Within a day: big first, then the source name and position of the story's first item on that day (the "newsletter order"; it is alphabetical by source key, so Alpha Signal before TLDR).
- The title and explanation come from the first item, oldest first, that has a stored headline or explanation; the stored note sits on the item that carries the Telegram key (`story[0]`). The fallback title is the oldest item's title.
- Items without a story count as stories of one.
- `badges` is a list; only `"big"` exists until 002/04. `items` are `{emailId, position}`, the form 002/03 needs; `key` is the first item's `emailId:position`.
- The note is upserted with `headline` and `explanation` only, so classification columns are never overwritten. A failed model call stores no note.
- `summary.explain` returns the parsed headline and explanation (or None) and `summary.message` builds the text from it; `news_text` composes them so the demo button is unchanged. `store.explained` returns the row and its note.
- Alembic revision id `4d8e2a7f9b13` was chosen by hand (no autogenerate in this run).

## Verified
2026-11-05, unattended run: fast tests only, with no app or database. The migration was hand-written and not applied, and the list SQL was compiled for Postgres but never executed. PR: https://github.com/borbalita/folio/pull/106. Left unticked because checks were skipped.

- Story on two days appears once, on the newer day (test): pass, `test_a_story_with_items_on_two_days_appears_once_on_the_newer_day`.
- Window boundary: story on one page only (test): pass, `test_a_story_crossing_the_window_boundary_is_on_one_page_only`, `test_the_window_reads_all_items_of_every_story_that_touches_it`.
- `only=big` (test): pass, `test_only_big_keeps_stories_both_newsletters_cover`.
- Empty blurb on one item (test): pass, `test_the_blurb_is_the_longest_non_empty_one`.
- Explanation survives re-embed and rebuild (test): pass, `test_the_explanation_survives_re_embedding_and_rebuilding`, `test_notes_are_joined_on_the_email_and_position_not_on_ids`. These check the join key in the compiled SQL, not a real re-embed.
- 403 without a mailbox; other users' items never appear (test): pass, `test_a_user_without_an_active_mailbox_gets_403`, `test_the_outer_query_is_scoped_to_the_mailboxes_as_well_as_the_window`. Scoping is checked on the compiled SQL, not against real rows.
- RLS on the new table (test): pass, `tests/database/test_rls_migration.py`.
- Owner opens AI News: days, Big filter, explanation, links, "Load older" (browser): **skipped**, the app wasn't started.
- Demo account sees its own stories with Big badges and no explanations (browser): **skipped**, the app wasn't started.
- Full fast suite: 1070 passed; ruff, tsc and eslint clean.
- Still to do before applying: `uv run alembic check` against a database, because the migration wasn't autogenerated.

2026-11-06, browser checks on the local app against the test Supabase project, signed in as the demo user. The migration applied cleanly and `uv run alembic check` found no drift. Explanations were hand-added test notes, because demo items never get real ones.

- Days, Big filter, explanation, links, "Load older" (browser): pass on demo data. Nine days newest first, Big narrowed 25 stories to 7, an explanation expanded, 36 links open in a new tab, and "Load older" added Oct 23 and then disappeared. **The criterion names the owner, and their real stories weren't checked**, so the task stays unticked until they repeat it.
- Demo account sees its own stories with Big badges and no explanations (browser): pass. Only the two stories with hand-added notes showed an explanation.
