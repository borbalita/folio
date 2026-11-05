# Telegram notifications — overview

What Folio sends to the owner's Telegram today and why it works the way it does. The design and its decisions are in [plan 001](plans/001-telegram/README.md).

## What it is

Push only: Folio messages the owner, and the owner never writes to the bot. Four events send a message:

| Event | When | Message |
|---|---|---|
| New invoice | An invoice email was extracted into Finance | `🧾 New invoice: Stadtwerke, €49.90, due 30 Oct` and a link to the invoice; `· due soon` when it is due within 3 days |
| New invoice, data missing | The invoice came in as `needs_info` | `🧾 New invoice from <sender>: details missing, check it in Folio` and the link |
| Due soon | An open invoice is due in 3 days or fewer (Berlin dates) | `⏰ Due in 3 days: Stadtwerke, €49.90 (30 Oct)` and the link |
| Big AI news | A story covered by both TLDR and Alpha Signal | `📰 <headline>`, a plain-words explanation of the story (what happened, terms explained, why it matters) written from the newsletters' text, and the links that exist |
| AI security news | A story the classifier marks as a new security incident or a real update of one (scope below) | `🔒 <headline>` or `🔒 Update: <headline>`, the same kind of explanation plus who is affected and what to do when the newsletters say so, and the links |

Each event is sent once, ever. A story that is both big and security sends one `news_security` message, not two. Invoices that arrive already paid send nothing. Invoice messages never contain the IBAN, the payment reference or email text. News messages paraphrase newsletter text: the explanation is written by a model from it, and may add plain-word definitions and why the story matters.

## When it runs

Security scope: AI as target, tool or cause of harm (sandbox escapes, malicious AI tooling, model misuse, critical flaws found by AI), active exploitation, critical flaws in widely used software, and large breaches or hacks. Not: advice and opinion pieces, security products and partnerships, bug bounty programmes, routine patches, stories that only mention security. Quiet hours apply like for every message.

Everything happens at the end of each email-ingest run (Railway cron, every 30 minutes), after invoices are extracted and matched and news stories are rebuilt:

1. **Classify.** Newsletter items from the last 2 days that are not demo items and have no verdict yet go to one structured call (the newsletter-extraction model) with their titles and blurbs and the headlines of the last 7 days of alerts. Per item it says whether it is a security story and, if so, `new`, `update` or `repeat` (an incident already alerted, with nothing material added). Results are stored per newsletter email and position in `news_item_notes`, so re-embedding doesn't re-classify. If the call fails, its error type is logged, nothing is stored and the next run asks again; everything below still runs. `python -m ingest.news_security --days 30` marks older items for the dashboard badges: it stores the security mark only, never an alert status, never sends, works one day at a time and leaves the last 2 days to this step.
2. **Detect.** New events become rows in `notifications`. Each row's key is unique (`invoice_new:<invoice id>`, `invoice_due:<invoice id>`, `news:<newsletter email id>:<position>`, shared by Big and Security), so an event can't be recorded twice however often ingest runs.
3. **Summarise.** A new big or security story gets one structured model call (the newsletter-extraction model). It reads the whole text of each newsletter the story's items came from, once per newsletter, with the story's titles named as the focus. If it fails for any reason, the message carries the first headline, its blurb when there is one, and the links instead.
4. **Send.** Pending rows go to Telegram, oldest first, one a second.

A notification problem never fails ingest. Each `job_runs` row of `email_ingest` counts `news_classified` (items answered by the classifier), `notifications_new`, `notifications_sent`, `notifications_failed` and `notifications_held`, or `notifications_error` when the step itself broke.

## Why news is keyed by email and position

News stories are deleted and rebuilt on every ingest run, and news items get new ids when they are re-embedded. Neither id is stable. Links can't identify an article either: most Alpha Signal items have none. An item's newsletter email and its position in it survive both, so a story is announced once even when it is rebuilt, re-embedded or gains an item later. That includes a story that gains a security item after its message went out: nothing more is sent. Only stories seen in the last 2 days are considered, so re-ingesting old mail never announces old news.

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

Telegram sees payees, amounts, due dates, news headlines and explanations, and security alerts; bot messages are not end-to-end encrypted. Message texts are stored only in `notifications` (RLS on, no policies). Logs carry kinds, counts and error types, never message text: a notification error is logged by its type, because database errors carry the values being written. The bot token is part of Telegram's request URL, so a filter removes it from httpx's request log. The summary and classification calls, like newsletter extraction, call the OpenAI SDK directly and are not traced. OpenAI receives the newsletter titles and blurbs for classification.

## Code

- `backend/app/notifications/detect.py`: which events are due, and the message texts (pure functions).
- `backend/app/notifications/store.py`: reads invoices and big or security stories, classifies new items, records rows.
- `backend/app/notifications/summary.py`: the big and security explanation call.
- `backend/app/notifications/security.py`: the classification call and its rubric.
- `backend/ingest/news_security.py`: the 30-day backfill of security marks.
- `backend/app/notifications/telegram.py`: the sender, quiet hours, retries, token redaction.
- `backend/ingest/email/run.py`: `_notify`, the step at the end of each scheduled run.
- `backend/ingest/notify/`: the setup command.
