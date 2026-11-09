# 002/02 — News dashboard: implementation plan

Task: [02-dashboard.md](02-dashboard.md). Spec: [README](../README.md), Design.

- **Table:** `NewsItemNote` (`news_item_notes`), primary key `(email_id, position)`, cascade from `emails`; `headline`, `explanation`, `security`, `alert_status` all nullable. Hand-written migration chained from `01b8354147e4`, with `RLS_TABLES`.
- **Notify step:** `summary.explain` returns the parsed headline and explanation (or none on failure); `news_text` stays the message builder on top of it. `store.explained` also returns the note for the announcing item (`story[0]`), and `record_notifications` upserts it with `headline` and `explanation` only.
- **List building:** `app/database/news_feed.py`. A pure `build_days(items, before, days, only_big)` groups a user's items by story, puts each story on its newest day, keeps the stories whose newest day is in `[before - days, before)`, and assembles title, blurb, badges, links, item refs and explanation. A thin loader reads the user's items (stories that touch the window, all their items) joined to notes by `(email_id, position)`.
- **Route:** `GET /news/stories` in `app/api/news.py`, behind `require_news_access`, mailbox-scoped.
- **Frontend:** `api.listNewsStories`, a `NewsDashboard` page for the `/news` index route, `agents.ts` texts.

Tests (red first): `tests/database/test_news_feed.py` (the list-building criteria), `tests/api/test_news_dashboard.py` (403 and scoping), `tests/notifications/test_store.py` (note written with the message), `tests/database/test_rls_migration.py` (existing; fails until the migration lists the table).
