# 001/05 Demo newsletters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The finance demo user gets AI News with two fictional newsletters, seeded by the demo reset, isolated from the owner's stories and Telegram summaries, plus a presenter button that sends a demo news summary to Telegram.

**Architecture:** News gets its own mailbox scope (all active mailboxes, demo included), like Finance's invoice scope. Two new newsletter sources join the existing check constraints. The story build and the Telegram planner read only non-demo items; "big" becomes "both newsletters of one pair". A committed JSON fixture of invented items with precomputed embeddings is written by the finance demo reset as emails, items and finished stories. A demo route builds a summary of the demo's big stories and posts it to the owner's Telegram chat.

**Tech Stack:** FastAPI, SQLAlchemy 2.1 + Alembic, pgvector, OpenAI embeddings (fixture script only), React/TS.

**Spec:** [../README.md](../README.md), task [05-demo-newsletters.md](05-demo-newsletters.md); finance demo spec [003](../../../../05-finance/plans/003-finance-demo/README.md).

## Global Constraints

- No new dependencies. Settings only through `backend/app/config.py`.
- Newsletter names are fictional: "The Daily Tensor" (`demo_tensor`), "AI Detective" (`demo_detective`); items are the owner's real news, rephrased; links to original articles or newsrooms, never `tldrnewsletter.com` or `utm_` tracking; never TLDR or Alpha Signal names in demo data.
- Seeding makes no model calls: embeddings come from the committed fixture. Only the fixture script (run once, owner's OK) and the Telegram button (one summary call) call models.
- Migrations: `uv run alembic revision -m ...`, hand-written check-constraint ops only (autogenerate can't see them); the owner applies them.
- Demo data stays the demo user's: nothing in the owner's stories, retrieval or automatic notifications changes because demo rows exist.
- Tests from `backend/`: `set -a && . ./.env.example && set +a && EMAIL_RERANK=false OPENAI_API_KEY=sk-invalid-for-tests uv run pytest -m "not integration"`; ruff. Frontend: `pnpm exec tsc --noEmit`, `pnpm lint`. Unique test module names across `tests/`.

## Review Focus

1. **A cron run right after a demo reset** must not touch demo stories (they'd be deleted as "not referenced" if the build loads only non-demo items but still deletes every unreferenced story) → test in Task 3 that a story referenced only by demo items survives a rebuild.
2. **The owner's own story that happens to match a demo item** (same lab, same day) must never merge with it → covered by excluding demo items before clustering; test in Task 3.
3. **Embedding model or dimensions changed in settings** while the fixture holds old vectors → seeding refuses with a clear error instead of inserting wrong-sized vectors; test in Task 4.
4. **Telegram button with Telegram unset** (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` missing locally) → 409 with a plain message, no crash; test in Task 6.
5. **Reset twice** must not leave orphaned demo stories (stories aren't deleted by the email cascade: `news_items.story_id` is `SET NULL`) → the reset deletes demo stories explicitly; integration test in Task 5.

---

### Task 1: News reads its own mailbox scope

**Files:** `backend/app/database/mailboxes.py`, `backend/app/auth/email_access.py`, `backend/app/news_assistant/tools.py`; tests `backend/tests/api/test_news_access.py` (new), existing email/news tests that patch `active_mailbox_ids` for News.

**Interfaces:** produces `mailboxes.news_mailbox_ids(user_id) -> list[UUID]` (all active mailboxes incl. `demo`, same query as `invoice_mailbox_ids`; reuse it if identical: `news_mailbox_ids = invoice_mailbox_ids` is fine only if a comment says why both scopes are equal), `require_news_access(user) -> list[UUID]` (403 when empty).

- [ ] Tests: demo user (only a demo mailbox) → `/me` agents `["documents", "news", "finance"]`, no `email`; owner with a Yahoo mailbox → `documents`, `email`, `news` (+ `finance`) as today; `require_agent_access(user, "news")` uses the news scope; news tools' filters carry `news_mailbox_ids`.
- [ ] Implement; full suite green; commit `feat(news): AI News reads its own mailbox scope, demo included`.

### Task 2: Demo newsletter sources and paired "big"

**Files:** `backend/app/database/models/email/message.py` (`NewsletterSource.DEMO_TENSOR = "demo_tensor"`, `DEMO_DETECTIVE = "demo_detective"`), migration `<rev>_demo_newsletter_sources.py` (drop/create `ck_emails_newsletter_source` and `ck_news_items_source` with all four values), `backend/ingest/email/stories.py` (`is_big`), `backend/app/retrieval/news/formatting.py` and `backend/app/notifications/detect.py` (display names); tests in the existing stories/formatting test modules.

**Interfaces:** produces `NEWSLETTER_PAIRS: tuple[frozenset[str], ...] = (frozenset({"tldr", "alpha_signal"}), frozenset({"demo_tensor", "demo_detective"}))` in `stories.py`; `is_big(items)` is true when the items' sources contain one whole pair. Display names `"demo_tensor": "The Daily Tensor"`, `"demo_detective": "AI Detective"` in both name maps. Retrieval's per-user `count(DISTINCT source) > 1` stays (a user only ever has one pair).

- [ ] Tests: TLDR + Alpha Signal → big; Tensor + Detective → big; TLDR + Detective → not big; one source → not big; coverage line "The Daily Tensor only · …".
- [ ] Migration with hand-written ops and downgrade (downgrade requires deleting demo-source rows first; say so in its docstring); commit `feat(news): demo newsletter sources; big means both newsletters of a pair`.

### Task 3: The story build and Telegram summaries skip demo items

**Files:** `backend/ingest/email/stories.py` (`rebuild_stories`), `backend/app/notifications/store.py` (`load_big_stories`); tests in the existing stories and notifications store test modules.

**Interfaces:** `rebuild_stories` loads only items whose email's mailbox provider is not `demo`, and deletes only stories that were referenced by those items or by none at all *and* are not referenced by any demo item (a story referenced only by demo items is never touched). `load_big_stories` joins item → email → mailbox and excludes `provider = 'demo'`.

- [ ] Tests (compiled SQL as in `tests/database/test_bank_connections.py`, plus a small in-memory fake for the deletion rule): the item query excludes demo mailboxes; a story referenced only by demo items survives `rebuild_stories`; an owner item and a demo item on the same topic and day never end up in one planned story; `load_big_stories` SQL carries the demo exclusion.
- [ ] Commit `fix(news): the story build and Telegram summaries leave demo news alone`.

### Task 4: The demo news fixture and its embedding script

**Files:** `backend/app/demo/news_fixture.json` (generated, committed), `backend/app/demo/news_fixture.py` (loader), `backend/app/demo/embed_news_fixture.py` (one-off script); test `backend/tests/demo/test_demo_news_fixture.py`.

**Interfaces:**
- Fixture JSON: `{"embedding_model": str, "embedding_dimensions": int, "items": [{"key": str, "story": str, "source": "demo_tensor"|"demo_detective", "days_ago": int, "position": int, "title": str, "blurb": str, "url": "https://example.com/...", "embedding": "<base64 float32>"}]}`.
- Content (changed 2026-10-22, owner): the 37 rephrased real items already drafted in `news_fixture.draft.json` (7 big stories, 3 spanning several days, security and new-model news for the demo questions); English text as the real newsletters.
- `load_fixture() -> list[FixtureItem]` refuses (`ValueError`) when `embedding_model`/`embedding_dimensions` differ from settings.
- `python -m app.demo.embed_news_fixture`: reads the text-only draft (`news_fixture.draft.json`, committed), embeds `embed_text(item)` exactly as `_write_news_items` does (`ingest/email/news.py`), writes `news_fixture.json`. Run once with the owner's OK (OpenAI cost ≈ cents).

- [ ] Tests: counts and shape (37 items, big stories ≥ 7 with both sources, multi-day stories ≥ 3, at least 5 security and 5 new-model items by keyword, no URL on `tldrnewsletter.com` or with `utm_`, no "TLDR"/"Alpha Signal" in any text); every vector decodes to `settings.openai_embedding_dimensions` floats; mismatched model → `ValueError`.
- [ ] The draft exists (written in the main session from the owner's export); run the script with the owner's OK, commit both files; commit `feat(news): demo news fixture with precomputed embeddings`.

### Task 5: The demo reset seeds AI News

**Files:** `backend/app/demo/news_state.py` (rows), `backend/app/demo/base_state.py` (add news rows to `BaseRows` groups), `backend/app/demo/reset.py` (delete demo stories first); tests `backend/tests/demo/test_demo_news_state.py`, extend `tests/demo/test_demo_reset.py` and `tests/demo/test_demo_reset_integration.py`.

**Interfaces:** `build_news_rows(today, accounts, *, to_address) -> NewsRows(emails, items, stories)`: one `ai_newsletter` email per newsletter per day (subject "The Daily Tensor — {date}" / "AI Detective #{n}", `newsletter_source` set, body = the day's items as text, sent 07:00 local), items with `edition_date = today - days_ago`, `story_id` set, fixture vectors; one `NewsStory` per fixture story with `first_seen`/`last_seen` from its items and `is_big` from `stories.is_big`. Groups insert order: emails → stories → items. `reset_demo` deletes `NewsStory` rows referenced by the demo mailbox's items before deleting the emails.

- [ ] Tests: counts per story kind; dates move with today; every item's story in the build; `is_big` matches the pair rule; reset statements now include the story delete scoped through the demo mailbox, before the email delete; integration (local eval DB): two resets leave exactly the fixture's stories for the demo, none orphaned, and an owner story untouched.
- [ ] Commit `feat(demo): the demo reset seeds AI News`.

### Task 6: "Send news summary to Telegram" on the presenter page

**Files:** `backend/app/demo/news_telegram.py`, `backend/app/api/demo.py` (`POST /finance/demo/news-summary`), `backend/app/notifications/telegram.py` (extract `send_text(text) -> None` from `send_pending` if needed), `frontend/src/pages/finance/DemoPresenterPage.tsx`, `frontend/src/lib/api.ts`; tests `backend/tests/demo/test_demo_news_telegram.py`, `backend/tests/api/test_demo_news_route.py`.

**Interfaces:** `send_demo_summary(user_id) -> dict` loads the demo mailbox's big stories of the last 7 days (as `NewsItemFacts`), builds the text with `summary.news_text(items)` for the most covered story (falls back as the real summaries do), posts it with `send_text`, returns `{"sent": True, "headline": ...}`; 409 "Telegram is not configured" when token or chat id is missing; 404 "No big demo stories" when none. Ignores quiet hours; writes no `notifications` row. The route sits behind `require_demo_user`. Presenter page: a "News" block with "Send news summary to Telegram" and the result line.

- [ ] Tests: only demo-mailbox stories are loaded (SQL), the text goes to `settings.telegram_chat_id` via a fake HTTP client, no notification row is added, 409 without Telegram settings, route 404/403/200 like the other demo routes.
- [ ] Frontend `tsc`/`lint`; commit `feat(demo): send a demo news summary to Telegram`.

### Task 7: Verify and record (main session)

- [ ] Every `(test)` criterion in [05-demo-newsletters.md](05-demo-newsletters.md) maps to a passing test.
- [ ] Owner applies the migration; `alembic check` clean.
- [ ] `(browser)` locally as the demo user after a reset: AI News card present; "What were the big stories this week?" shows invented big stories with "both newsletters" lines; a citation opens. `(manual)`: the Telegram button delivers a summary to the owner's chat.
- [ ] Privacy page: unchanged (no new data, service or recipient); note it in the PR.
- [ ] Verified section; tick 001/05 in the news spec.
