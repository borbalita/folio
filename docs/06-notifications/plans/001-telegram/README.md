# 001 — Telegram notifications: invoices and big AI news

- Created: 2026-10-19
- Status: Ready
- Current stage: Implementation; 001/01 to 001/03 done

## Approval state

- 2026-10-19: in chat, the owner chose push only, instant messages, new-invoice and due-soon events, big news only, and payee, amount and due date in messages. They approved the assumptions (3 days, quiet hours 22:00–07:00 Berlin, no flood at launch) and the outbox approach. Big-news messages carry a summary of both newsletters (owner's addition).
- 2026-10-19: the owner approved the written spec; the plan is Ready.
- 2026-10-19: after the code review, news is keyed per article (newsletter email and position) with a 2-day window, a `429` stops the run, and the tracing line is corrected (owner to confirm).

## Problem

New invoices and big AI news reach Folio by email, but the owner only learns about them by opening the app. Invoices can sit unnoticed until they are overdue. The owner wants a short message on their phone as soon as something needs attention.

## Current system

- **Invoices:** email ingest (Railway cron, every 30 minutes) labels invoice emails and extracts one or more invoices per email ([invoices.py](../../../../backend/ingest/email/invoices.py)). Each invoice has `status` (`open`, `needs_info`, `paid`), payee, amount, currency and due date ([invoice.py](../../../../backend/app/database/models/finance/invoice.py)).
- **Big news:** ingest stores newsletter items (title, blurb, url, source) and rebuilds `news_stories` on every run ([stories.py](../../../../backend/ingest/email/stories.py)). A story is big when both TLDR and Alpha Signal cover it (`is_big`). Rebuilding deletes and recreates stories, so a story's id is not stable.
- **Notifications:** only the bank-expiry emails from 001/11 in 05-finance, sent through Yahoo SMTP ([notify.py](../../../../backend/app/finance/notify.py)), once per stage, retried on failure.
- **Jobs:** each ingest run is recorded in `job_runs` with counts.

## Goals and non-goals

Goals:

- Within about 30 minutes of arriving, every new invoice reaches the owner on Telegram with payee, amount and due date, or a note that data is missing.
- An open invoice is reminded once, 3 days before it is due.
- Every big AI story reaches the owner once, as a short summary of both newsletters with their links.
- No message is sent twice, none is lost to a Telegram or model outage, and nothing is sent at night.

Non-goals: buttons or commands in Telegram; asking the assistants from Telegram; overdue or paid messages; topic or model-rated news; moving the bank-expiry emails to Telegram; more than one recipient.

## Key concepts

- **Telegram Bot API.** A bot created with @BotFather has a token. `POST https://api.telegram.org/bot<token>/sendMessage` with `chat_id` and `text` sends a message. A bot can only message a chat that has written to it first; `getUpdates` shows that chat's id.
- **Delivery.** Bot messages pass through Telegram's servers and are not end-to-end encrypted.
- **Rate limits.** At most about one message per second to one chat; `429` answers carry `retry_after`.

## Decisions

- **Push only.** Rejected: buttons (needs an inbound webhook and caller checks) and chat in Telegram.
- **Instant per event, within one ingest run (about 30 minutes).** Rejected: a daily digest.
- **Events:** new invoice (including `needs_info`) and due soon (3 days before, once, only while open). Rejected for now: overdue and paid.
- **News:** stories already marked big. Rejected: topic lists and model-rated importance.
- **Message content:** payee, amount, due date and a link. Never the IBAN, the reference or email text. Rejected: minimal messages, and full messages with payment details.
- **Big news is summarised:** one model call per big story, on the model newsletter extraction uses; a failed call sends the headline and links without a summary.
- **Outbox table, sent from the email-ingest cron.** Rejected: sending at the point of detection (no retry, couples ingest to Telegram), and a separate notifier service (another Railway service, and diffing state).
- **Quiet hours 22:00–07:00 Europe/Berlin;** held messages go out with the first run after 07:00.
- **No flood at launch:** everything that exists when the migration runs counts as already sent.

## Design

```text
Email ingest (cron, 30 min)
  ├─ extract invoices, rebuild stories (existing)
  ├─ detect events ──► notifications (unique key per event)
  │     invoice_new:<invoice id>   invoice_due:<invoice id>   news:<email id>:<position>
  └─ send due rows ──► Telegram sendMessage   (held 22:00–07:00 Berlin, retried next run)
```

- **Table `notifications`** (RLS on): `id`, `key` (unique), `kind` (`invoice_new`, `invoice_due`, `news_big`), `text`, `status` (`pending`, `sent`, `failed`, `skipped`), `attempts`, `last_error` (error type only), `created_at`, `sent_at`.
- **Detection** runs after extraction and story building in each ingest run, and records rows only:
  - **New invoice:** any invoice without an `invoice_new` row. Wording for `open`: "🧾 New invoice: {payee}, {amount}, due {date}". When it is due within 3 days, "· due soon" is added and its `invoice_due` row is recorded as `skipped`, so it gets one message. Wording for `needs_info`: "🧾 New invoice from {sender}: details missing, check it in Folio".
  - **Due soon:** an `open` invoice with a due date at most 3 days ahead (Berlin dates) and no `invoice_due` row. Wording: "⏰ Due in {n} days: {payee}, {amount} ({date})".
  - **Big news:** a big story seen in the last 2 days whose articles have no `news:` row yet gets one message; a row is recorded per article (`news:<newsletter email id>:<position>`), so the message is attached to the first one and the others are `skipped`. Keys are per article, not per story or news item id, because stories are rebuilt and items re-embedded with new ids; links can't serve, since most Alpha Signal items have none. Messages list only the links that exist. A rebuilt story, a re-embedded item or a story that gains an item is not announced again, and a backfill of old mail never announces old news.
  - Each invoice message links to `{APP_URL}/finance/invoices/{email id}`.
- **News summary:** a structured model call on the story's items (title and blurb only) returns a headline and 2–3 sentences. Message:
  ```text
  📰 {headline}
  {summary}
  TLDR: {url} · Alpha Signal: {url}
  ```
  A failed call (an API error, a content filter or length stop, or unparseable output) falls back to the first item's title and both links; the error type is logged.
- **Sending** happens after detection: pending rows, oldest first, through `sendMessage` (`httpx`, 10 s timeout), one at a time.
  - **Quiet hours:** between 22:00 and 07:00 Berlin nothing is sent.
  - **Failure:** a `5xx` or a network error counts an attempt and keeps the row pending; 5 attempts mark it `failed`. A `429` counts an attempt for that row and stops the run, so the rest keep their attempts.
  - A `4xx` other than `429` (a bad token or chat id) marks the row `failed` at once, and the run logs `telegram_misconfigured`.
  - Sending never fails the ingest job. `job_runs.counts` gains `notifications_new`, `notifications_sent` and `notifications_failed`.
- **Configuration:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `APP_URL` in `config.py`. With any of them missing, new rows are recorded as `skipped`, so turning Telegram on later doesn't send old events. The `email-ingest` Railway service already references every backend variable.
- **Setup command:** `python -m ingest.notify --chat-id` prints the chat ids from the bot's `getUpdates`, after the owner has messaged the bot.
- **Migration:** creates the table and records a `sent` row for every existing invoice, every open invoice due within 3 days, and every article of an existing big story.
- **Privacy:** Telegram sees payees, amounts, due dates, news headlines and summaries. Message texts live only in `notifications` (RLS). Logs carry kinds, counts and error types, never text. The summary call, like newsletter extraction, calls the OpenAI SDK directly and is not traced. A notification error is logged by type only: database errors carry bound parameters.
- **Dependencies:** none new (`httpx`, PydanticAI and the OpenAI SDK are already used).

## Success criteria

1. A real invoice email reaches Telegram within 30 minutes (outside quiet hours) with payee, amount, due date and a working link, or with the details-missing wording.
2. An open invoice due in 3 days is reminded once, and never twice across runs.
3. A big AI story reaches Telegram once, with a summary and both newsletter links, and is not repeated after later ingest runs.
4. Nothing is sent between 22:00 and 07:00 Berlin; held messages arrive after 07:00.
5. With Telegram down or misconfigured, ingest still succeeds and the failure is visible in `notifications` and `job_runs`.
6. Turning notifications on for the first time sends nothing old.

## Tasks

- [x] [001/01 — Notifications table, event detection and launch baseline](tasks/01-detection.md)
- [x] [001/02 — Big-news summaries](tasks/02-news-summary.md) — after 01
- [x] [001/03 — Telegram sender with quiet hours and retries](tasks/03-sender.md) — after 01
- [ ] [001/04 — Wire into email ingest; settings and setup command](tasks/04-wiring.md) — after 02, 03
- [ ] [001/05 — Overview and end-to-end check](tasks/05-overview.md) — after 04

```text
01 ─┬─► 02 ─┐
    └─► 03 ─┴─► 04 ─► 05
```

## Open questions and risks

- **Stories regrouped differently:** if a rebuild merges two announced stories, or splits one, the item-level keys stop a repeat; a story gaining a new item from the other newsletter later is not re-announced.
- **The summary model writes something inaccurate:** it sees only the two newsletters' headlines and blurbs, and both links are in the message for checking. Next action: read the first week's summaries.
- **The Telegram token leaks:** someone could send messages as the bot, but can't read Folio. Rotate it with @BotFather. It is only in `.env` and Railway.
