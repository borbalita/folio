# 001/01 Demo mail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The demo user gets the Email Assistant over 40 invented emails seeded by the demo reset, with doctor's appointments always placed in the reset day's month.

**Architecture:** The Email scope stops excluding demo mailboxes. A committed fixture holds the 40 emails with labels, day offsets and appointment placeholders, plus one precomputed embedding per email. A seeding module renders the placeholders for the reset day and writes emails and chunks into the demo mailbox as part of `BaseRows`.

**Tech Stack:** SQLAlchemy, pgvector, OpenAI embeddings (one-off script), pytest.

**Spec:** [../README.md](../README.md), task [01-demo-mail.md](01-demo-mail.md).

## Global Constraints

- No new dependencies; no model calls at reset; the embedding script runs once with the owner's OK.
- People, practices and companies are fictional, on `.example` domains; Dr. Rothenbach and Eisenhalle Fitness reuse the demo vendors. Private mail German, work mail English.
- The owner's Email scope and access are unchanged.
- German dates without locale dependencies (own weekday and month name tables).
- Tests from `backend/` as in the other demo plans; unique test module names.

## Review Focus

1. **Reset on the last day of a month**: appointments may then lie in the past within the month; the confirmation email must still be sent before its appointment → test over every day of a 31-day, a 30-day and a February month.
2. **Weekend appointments** look odd → appointments move to the nearest weekday within the same month; test.
3. **Two appointments on the same day and time** would confuse the answer → distinct slots; test.
4. **The owner's Email search** must not include anything new: the owner has no demo mailbox, so the query only loses a filter; test that the compiled query still scopes by the user id.
5. **Rendered text vs embedded text** differ only in dates: the embedding script renders the draft for a fixed reference day; test that it uses the same renderer as seeding.

---

### Task 1: Email scope includes the demo mailbox

**Files:** `backend/app/database/mailboxes.py`, tests in `backend/tests/database/test_mailboxes.py`, `backend/tests/api/test_news_access.py` (or the email access tests).

- [x] Tests: `active_mailbox_ids`' statement scopes by user id and `is_active` and has no provider condition; the demo user (only a demo mailbox) gets `/me` agents `["documents", "email", "news", "finance"]`; the owner's agents are unchanged.
- [x] Remove the provider filter; keep `invoice_mailbox_ids`/`news_mailbox_ids` (now equal to `active_mailbox_ids`; leave a comment, don't merge them in this task).
- [x] Commit `feat(email): the demo user's mailbox counts for the Email Assistant`.

### Task 2: Fixture, loader and embedding script

**Files:** `backend/app/demo/mail_fixture.draft.json` (written in the main session), `backend/app/demo/mail_fixture.py`, `backend/app/demo/embed_mail_fixture.py`, `backend/app/demo/mail_dates.py`; test `backend/tests/demo/test_demo_mail_fixture.py`, `backend/tests/demo/test_demo_mail_dates.py`.

**Interfaces:**
- Draft: `{"emails": [{"key", "from_name", "from_address", "subject", "body", "label", "days_ago", "appointments": {"<name>": {"month": "this"|"next", "slot": 0.0–1.0, "time": "HH:MM"}}}]}`; placeholders in subject/body: `{name}` (e.g. `"Montag, 12. Oktober 2026, 09:30 Uhr"`) and `{name:short}` (`"12.10."`). A moved appointment uses two names (`physio_old`, `physio_new`, `slot` old < new).
- `mail_dates.appointment_dates(rules, today) -> dict[str, datetime]`: "this" → day `1 + round(slot × (days_in_month − 1))`, weekend → nearest weekday in the month; "next" → same rule in the next month; local time from `time` in `settings.email_timezone`. `render(text, dates) -> str` fills both placeholder forms (German weekday and month names).
- `mail_fixture.load_fixture(path=...) -> list[FixtureMail]` (draft fields + `embedding`), refusing a model/dimension mismatch; `REFERENCE_DAY = date(2026, 10, 15)` used by the script to render text before embedding `"{subject}\n{body}"`.

- [x] Tests (dates): for every day of Oct 2026, Nov 2026 and Feb 2027: "this" dates fall in that month, "next" in the next, all on weekdays, distinct; `physio_old < physio_new`. `render` produces German weekday/month names.
- [x] Tests (fixture): 40 emails, keys unique, every sender on `.example`, labels in the allowed set, at least 2 `needs_reply`, 6 doctor emails, every placeholder used in a text has a rule; loader mismatch refusal; script's pure part uses `render` with `REFERENCE_DAY`.
- [x] Commit `feat(email): demo mail fixture, dates and embedding script`.

### Task 3: The reset seeds the demo mail

**Files:** `backend/app/demo/mail_state.py`, `backend/app/demo/base_state.py`; tests `backend/tests/demo/test_demo_mail_state.py`, extend `test_demo_reset.py` / `test_demo_reset_integration.py`.

**Interfaces:** `build_mail_rows(today, accounts, *, to_address) -> MailRows(emails, chunks)`: dates from `appointment_dates(..., today)`; `sent_at` = `today − days_ago` at 08:00–18:00 local (spread by key), but never later than one day before the earliest appointment the email mentions; label from the fixture; one `EmailChunk` per email (`chunk_index 0`, `chunk_text` = rendered `"{subject}\n{body}"`, `token_count` via tiktoken as `chunk_email_text`, fixture embedding). `BaseRows.groups()` puts mail emails before chunks.

- [x] Tests: 40 emails and 40 chunks in the demo mailbox; labels as the fixture; appointment emails sent before their appointments for every day of a month; flush order; integration test counts mail emails and chunks after two resets.
- [x] Commit `feat(demo): the demo reset seeds everyday mail`.

### Task 4: Verify (main session)

- [x] Owner OK → run `python -m app.demo.embed_mail_fixture`, commit `mail_fixture.json`.
- [x] Local browser check as the demo user after a reset: the doctor's question and the reply question.
- [x] Final whole-branch review; Verified section; tick 001/01 and set the plan Complete.
