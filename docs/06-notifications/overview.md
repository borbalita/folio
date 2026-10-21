# Telegram notifications — overview

What Folio sends to the owner's Telegram today and why it works the way it does. The design and its decisions are in [plan 001](plans/001-telegram/README.md).

## What it is

Push only: Folio messages the owner, and the owner never writes to the bot. Three events send a message:

| Event | When | Message |
|---|---|---|
| New invoice | An invoice email was extracted into Finance | `🧾 New invoice: Stadtwerke, €49.90, due 30 Oct` and a link to the invoice; `· due soon` when it is due within 3 days |
| New invoice, data missing | The invoice came in as `needs_info` | `🧾 New invoice from <sender>: details missing, check it in Folio` and the link |
| Due soon | An open invoice is due in 3 days or fewer (Berlin dates) | `⏰ Due in 3 days: Stadtwerke, €49.90 (30 Oct)` and the link |
| Big AI news | A story covered by both TLDR and Alpha Signal | `📰 <headline>`, a 2–3 sentence summary of both newsletters, and the links that exist |

Each event is sent once, ever. Invoices that arrive already paid send nothing. Messages never contain the IBAN, the payment reference or email text.

## When it runs

Everything happens at the end of each email-ingest run (Railway cron, every 30 minutes), after invoices are extracted and matched and news stories are rebuilt:

1. **Detect.** New events become rows in `notifications`. Each row's key is unique (`invoice_new:<invoice id>`, `invoice_due:<invoice id>`, `news:<newsletter email id>:<position>`), so an event can't be recorded twice however often ingest runs.
2. **Summarise.** A new big story gets one structured model call (the newsletter-extraction model) on the items' titles and blurbs. If it fails for any reason, the message carries the first headline and the links instead.
3. **Send.** Pending rows go to Telegram, oldest first, one a second.

A notification problem never fails ingest. Each `job_runs` row of `email_ingest` counts `notifications_new`, `notifications_sent`, `notifications_failed` and `notifications_held`, or `notifications_error` when the step itself broke.

## Why news is keyed by email and position

News stories are deleted and rebuilt on every ingest run, and news items get new ids when they are re-embedded. Neither id is stable. Links can't identify an article either: most Alpha Signal items have none. An item's newsletter email and its position in it survive both, so a story is announced once even when it is rebuilt, re-embedded or gains an item later. Only stories seen in the last 2 days are considered, so re-ingesting old mail never announces old news.

## Quiet hours, retries, failures

- **Quiet hours** are 22:00–07:00 Europe/Berlin. Nothing is sent then; held rows go out with the first run after 07:00.
- **A 5xx answer or a network error** counts an attempt and the row waits for the next run. After 5 attempts it is `failed` and stays in the table.
- **A 429 (rate limit)** counts an attempt for that row and stops the run, so the rest keep their attempts.
- **Any other 4xx** (a wrong token or chat id) fails the row, logs `telegram_misconfigured` and stops the run.

Rows are `pending`, `sent`, `failed` or `skipped`. `skipped` rows are recorded but never sent: events seen while Telegram is off, the second item of an announced story, the due-soon row of an invoice whose new-invoice message already said "due soon".

## Settings and setup

| Setting | Meaning |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The bot's token from @BotFather |
| `TELEGRAM_CHAT_ID` | The owner's chat with the bot |
| `APP_URL` | Where invoice links point, e.g. `https://folio.tasnadi-ai.de` |

Notifications are off unless all three are set. While off, new events are recorded as `skipped`, so turning them on later doesn't send old events. In Railway they are set on the backend service; `email-ingest` references them.

To set up a bot, from `backend/`:

1. Create it with @BotFather (`/newbot`) and put the token in `.env`.
2. Send the bot a message, then run `uv run python -m ingest.notify --chat-id` and put the printed id in `.env`.
3. Run `uv run python -m ingest.notify --test`: the bot sends "✅ Folio notifications are set up."

At launch, the migration recorded every invoice and big story that existed as already sent, so the first run sent nothing old.

## Privacy

Telegram sees payees, amounts, due dates, news headlines and summaries; bot messages are not end-to-end encrypted. Message texts are stored only in `notifications` (RLS on, no policies). Logs carry kinds, counts and error types, never message text: a notification error is logged by its type, because database errors carry the values being written. The bot token is part of Telegram's request URL, so a filter removes it from httpx's request log. The summary call, like newsletter extraction, calls the OpenAI SDK directly and is not traced.

## Code

- `backend/app/notifications/detect.py`: which events are due, and the message texts (pure functions).
- `backend/app/notifications/store.py`: reads invoices and big stories, records rows.
- `backend/app/notifications/summary.py`: the big-news summary call.
- `backend/app/notifications/telegram.py`: the sender, quiet hours, retries, token redaction.
- `backend/ingest/email/run.py`: `_notify`, the step at the end of each scheduled run.
- `backend/ingest/notify/`: the setup command.
