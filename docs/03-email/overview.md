# Email agent — overview

What the email agent does today and why it works the way it does. The full design is in [spec.md](spec.md).

## What it is

A second agent next to the document copilot. After sign-in, `/` shows an agent picker. The Email card is there only for a user who owns an active mailbox. The agent answers questions about that mailbox and about AI newsletters in it, and cites every claim. There is one mailbox today, a Yahoo inbox.

## Ingest

Run from `backend/`:

```bash
uv run python -m ingest.email --limit 50 --since 2026-09-01
```

- Reads INBOX over IMAP (`imap.mail.yahoo.com:993`, stdlib `imaplib`) with a Yahoo app password.
- `--since` filters first. Then `--limit` keeps the newest N. The default is 5, and `0` means no cap.
- `--scheduled` is the cron mode: no cap, fetches from `last_synced_at` minus 1 day (or the last 7 days if never synced), and writes one `job_runs` row per run. It can't be combined with `--limit` or `--since`.
- The first run creates the `mailboxes` row and gives it to `EMAIL_AGENT_OWNER_USER_ID`. Ingest exits at once if that setting, `YAHOO_EMAIL`, or `YAHOO_APP_PASSWORD` is missing. The API starts without them.
- Each message is parsed, labeled, chunked, and embedded in one transaction. The run prints a summary: fetched, skipped, new, re-embedded, count per label, attachments saved or skipped, news items, stories rebuilt.
- The IMAP side is an adapter that returns a provider-neutral `ParsedMessage`. The rest of the pipeline never knows it's Yahoo. Gmail or a work account would be a new adapter.

## Idempotency

A message is skipped when the mailbox, Message-ID, content hash, embedding model, and embedding dimensions all match what is stored. Running the same command twice does nothing the second time. Raising `--limit` only adds older mail. Changing the embedding model or dimensions re-embeds stored messages and rebuilds their news items.

Uniqueness is per mailbox. The same email in two mailboxes is stored twice, because each copy has its own label and its own access rule.

A message with no Message-ID is skipped and logged, since it can't be deduplicated.

## Labels

Each email gets exactly one label.

1. **Sender rule first.** A sender in `AI_NEWSLETTER_DOMAINS` is `ai_newsletter`, with `newsletter_source` set to `tldr` or `alpha_signal`. It does not go through the classifier.
2. **Everything else** gets one Jev choice (`TYPESAFE_LABEL_MODEL`, default `jev-latest`). The input is from, subject, attachment filenames, and a truncated body.

| Label | Meaning |
|---|---|
| `needs_reply` | A person expects an answer |
| `promotional` | Marketing or a sales newsletter |
| `newsletter` | Informational mailing that is neither an AI digest nor a pitch |
| `invoice` | A bill or payment request |
| `other` | Personal or transactional mail, no reply needed |

An invalid answer or a failed call is retried once. After that the email is stored as `other` and the failure is logged.

## AI newsletters: items and stories

**Items.** Each `ai_newsletter` email goes through one structured call that returns its items in order, `{title, blurb, url}`, with sponsor blocks dropped. Each item is a `news_items` row, embedded as `title + "\n" + blurb` with the same model as other mail. `edition_date` is the send date in `EMAIL_TIMEZONE` (default `Europe/Berlin`).

**Stories.** Items are paired only across sources, TLDR with Alpha Signal, and only within `NEWS_MATCH_WINDOW_HOURS` (default 48). Jev decides whether two items are the same story. Connected pairs form one story. An item with no pair is a story on its own. A story is **big** (`is_big`) only when both sources covered it. Two TLDR items are never merged with each other.

Stories in the affected window are deleted and rebuilt on each run, so a morning TLDR can join the previous evening's Alpha Signal. Citations point at `news_items`, never at stories, so a rebuild never breaks a citation. The run logs how many pairs were checked and which ones Jev matched.

## Chat

The email agent is a sibling of the copilot in `backend/app/email_assistant/`. The orchestrator picks it from `chat_threads.agent`. It has three tools:

- `search_emails`: hybrid search (pgvector plus full-text, fused with RRF) over `email_chunks`, with filters for date range, label, sender, and mailbox.
- `list_big_news`: big stories in a date range.
- `search_news`: topic search over `news_items`, optionally only items in big stories.

Relative dates ("last week") are resolved in `EMAIL_TIMEZONE`. Grounding rejects an answer that cites an id the tools did not return, or cites one twice. Citations go to `email_citations`, which points at exactly one email chunk or one news item.

## Owner-only access

- A user has the Email agent when they own at least one active mailbox. `GET /me` returns `agents: ["documents"]` or `["documents", "email"]`.
- Every email route returns 403 to a user without a mailbox: thread list and create for `agent=email`, and posting to an email thread. Invoices and attachment downloads are Finance routes (`/finance/...`), owner-only.
- Every email query is scoped to the caller's active mailboxes. An invoice or attachment in another user's mailbox returns 403.
- Document routes don't depend on any of this.

## Invoices and attachments

- Every PDF attachment is saved at ingest, whatever the email's label, in `email_attachments` as `bytea`.
- **10 MB cap.** A PDF over `ATTACHMENT_MAX_BYTES` (default 10 MB) still gets a row with its filename and size, `content` null, and `skipped_reason = 'too_large'`. The invoice page lists it as "not stored (over 10 MB)".
- Invoices live in the Finance agent: `/finance/invoices` lists `invoice` emails, newest first, and `/finance/invoices/:emailId` shows from, subject, date, the body, and each stored PDF in an embedded viewer.
- PDFs come from `GET /finance/attachments/:id` (Finance owner only; old `/email/invoices/:emailId` links redirect), out of Postgres. Opening an invoice never contacts Yahoo.
- There is no pay action.

## Deferred

- Gmail, work mail, and storing credentials anywhere but config.
- A policy for ingesting full mailbox history.
- Paying invoices.
- Syncing deletes from the mailbox.
- Moving PDF bytes to Supabase Storage with signed URLs, if backups get heavy.
- Deduplicating news items across mailboxes, and showing the mailbox on a citation. Both wait for a second mailbox.
