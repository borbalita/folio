# 002/04 — Security alerts: implementation plan

Task: [04-security-alerts.md](04-security-alerts.md). Spec: [README](../README.md), Design.

- **Classifier:** `app/notifications/security.py`. One structured call through the OpenAI SDK, like `summary.py`, untraced. `classify(candidates, recent_alerts)` returns the answered items as `Classification(email_id, position, security, alert_status)`, or None on failure (error type logged). `parse` drops unknown or repeated indices.
- **Store:** `load_unclassified` (non-demo, from a date, no verdict, matched to the note by email and position), `load_recent_alerts` (7 days), `save_classifications` (security and alert_status only), `save_security_only` (backfill), `classify_recent` (the notify step's first half; 2-day lookback). `load_big_stories` becomes `load_stories`: big stories plus those with a `new`/`update` item, items carrying their `alert_status`.
- **Planning:** `StoryFacts.big` and `.alert` (`new` beats `update`). A story with an alert is `news_security` (with `update` for the prefix); otherwise big stories are `news_big` as before; shared `news:<email>:<position>` keys keep one message per story and nothing more after it went out.
- **Message:** `summary.explain(..., security=True)` appends the who-is-affected and what-to-do instruction; `detect.security_message` builds `🔒 [Update: ]headline`.
- **Migration:** hand-written `b7f3a2c9e154`, drops and recreates `ck_notifications_kind` with `news_security`.
- **Run:** `_notify` calls `classify_recent` before `record_notifications`; the job counts get `news_classified`.
- **Backfill:** `python -m ingest.news_security --days N`, one call per day, oldest first, security only, ending 2 days before today.
- **Dashboard:** `FeedItem.security`, `security` badge, `only=security`, order big, security, newsletter; frontend badge and Security filter.
- **Docs:** notifications overview, privacy page's Telegram line (date already 5 November 2026).

Tests (red first): `tests/notifications/test_security.py`, additions to `test_detect.py`, `test_store.py`, `test_summary.py`, `tests/ingest/test_news_security.py`, `tests/ingest/email/test_run.py`, `tests/database/test_news_feed.py`, `tests/api/test_news_dashboard.py`.
