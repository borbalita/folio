# 001 — Demo mail: the Email Assistant for the demo user

- Created: 2026-10-23
- Status: Complete
- Current stage: Done

## Approval state

- 2026-10-23: settled in chat: the finance demo user (plan [05-finance 003](../../../05-finance/plans/003-finance-demo/README.md)) also gets the Email Assistant, with 40 invented emails for the persona Kim Albrecht. The demo question the owner will ask is "Do I have any doctor's appointments this month?"; the rest of the mailbox is Claude's choice. Same pattern as [07-ai-news 001/05](../../../07-ai-news/plans/001-news-agent/tasks/05-demo-newsletters.md): a committed fixture with fixed labels and precomputed embeddings, seeded by the demo reset, isolated from the owner's mailbox. Design approved.

## Problem

The demo shows Finance and AI News, but not the Email Assistant: the demo user has no Email access, and the demo mailbox holds only invoice and newsletter emails, none of the everyday mail the Email Assistant is for. The owner wants to show it answering a real question from a believable mailbox.

## Current system

- **Email scope:** `mailboxes.active_mailbox_ids(user_id)` returns the user's active mailboxes except provider `demo`; it decides Email access (`require_email_access`, the `email` card in `agents_for`) and the Email Assistant's search scope (`app/email_assistant/tools/mail.py`). AI News and Finance have their own scopes that include the demo mailbox.
- **Search:** `app/retrieval/email` searches `email_chunks` (embedding of `"{subject}\n{body}"`, 512-token chunks, see `ingest/email/pipeline.py`) within `scope_clause(user_id, mailbox_ids)`, with optional label, sender and date filters. Labels: `needs_reply`, `promotional`, `newsletter`, `invoice`, `other`, `ai_newsletter`.
- **Demo mailbox today:** written by the demo reset (`app/demo/reset.py`, `base_state.py`, `news_state.py`): 9 invoice emails without chunks and the demo newsletters. The reset deletes the demo mailbox's emails (chunks cascade) before writing the base state.
- **Global readers of mail:** the email cron reads only the Yahoo mailbox; invoice and news notifications and the story build exclude demo mailboxes; `ingest/email/backfill_invoices.py` (manual) reads invoice emails globally (deferred from 003/03).

## Goals and non-goals

Goals:

- The demo user sees the Email Assistant, and its search covers the demo mailbox.
- After a reset, the demo mailbox holds 40 invented everyday emails with chunks and labels, dated relative to today.
- "Do I have any doctor's appointments this month?" finds exactly the current month's appointments, uses the new date of a moved appointment, and leaves out next month's.
- Nothing about the owner's mail, access or crons changes.

Non-goals: labelling or embedding the demo mail at reset time; replies or sending mail; demo mail for any other user.

## Decisions

- **Email scope includes the demo mailbox.** `active_mailbox_ids` stops excluding provider `demo`. The demo mailbox belongs only to the demo user, so the owner's scope is unchanged; the demo user's Email search also sees the invoice and newsletter emails, as a real mailbox would. Rejected: a demo-only special case in the Email tools, which adds a branch for no gain.
- **40 invented emails, fixed labels, precomputed embeddings,** in a committed fixture; no Jev or OpenAI calls at reset. A one-off script embeds them with the owner's OK, as for the news fixture.
- **Appointment dates are placed in the current month at reset.** The fixture holds appointment placeholders; the reset fills them so the "this month" appointments always fall in the month of the reset day, the moved appointment's new date also in it, and the "next month" one in the next month. Embeddings are computed from the text rendered for a reference date; the small date differences don't matter to semantic search.
- **Fictional people, practices and companies** on `.example` domains; the dental practice Dr. Rothenbach from the demo invoices reappears, so the demo world stays consistent. Private mail in German, work mail in English.

## Design

- **Mailbox (40 emails, about 3–4 weeks back from today):**
  - Doctors (6): dentist Dr. Rothenbach reminder (this month), GP check-up (this month), eye doctor (this month), a physiotherapy booking confirmation and its "Termin verschoben" email moving it to a later day this month, a dermatologist appointment next month, and "Ihre Laborwerte liegen vor" without an appointment.
  - Private, German (about 15): landlord (heating maintenance, meter reading), parcels, a restaurant reservation, a friend about the weekend, the gym (Eisenhalle Fitness, from the demo invoices), an online shop order, a bank notice without amounts, a library reminder, a neighbourhood flea market.
  - Work, English (about 12): a client project with open questions and a deadline (`needs_reply`), a team meeting, a conference invitation, a freelance enquiry, an invoice question from a client, a design review.
  - Promotional and newsletters (about 7): offers and shop newsletters (`promotional`, `newsletter`).
- **Fixture:** `backend/app/demo/mail_fixture.draft.json` (text, labels, sender, offsets, placeholders) and `mail_fixture.json` (+ one embedding per chunk, base64 float32, model and dimensions as in the news fixture).
- **Seeding:** `backend/app/demo/mail_state.py` builds emails and chunks for the demo mailbox, filling date placeholders by the rule above; `base_state.BaseRows` gains the mail rows; insert order emails → chunks.
- **Access:** `active_mailbox_ids` without the demo exclusion; tests updated so the owner's Email scope and the demo user's agent list (`documents`, `email`, `news`, `finance`) are pinned.
- **Failure modes:** the loader refuses a fixture whose embedding model or dimensions differ from settings; seeding makes no model calls.

## Success criteria

1. After a reset, the demo user sees the Email Assistant, and "Do I have any doctor's appointments this month?" lists the three current appointments and the moved appointment at its new date, not next month's, with citations.
2. A search by sender, label (`needs_reply`) or topic answers from the demo mail.
3. The owner's Email access and search are unchanged.

## Tasks

- [x] [001/01 — Demo mail fixture, Email access and seeding](tasks/01-demo-mail.md)

## Open questions and risks

- **The appointment question depends on the model reading dates correctly.** Next action: the browser check in 001/01; if it misses one, adjust the email wording (clear dates in subject and body), not the code.
- **`backfill_invoices.py --all/--detect` reads mail globally.** The demo mail has no PDFs and no invoice label, so it isn't touched; the demo invoices remain the case deferred in 003/03.
