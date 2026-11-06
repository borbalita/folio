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
