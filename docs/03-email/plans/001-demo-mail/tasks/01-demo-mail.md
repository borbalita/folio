# 001/01 — Demo mail fixture, Email access and seeding

## Goal
After a reset, the demo user's Email Assistant answers from 40 invented emails, including "Do I have any doctor's appointments this month?".

## Scope
- `active_mailbox_ids` includes the demo mailbox; the demo user gets `email` in `/me`.
- `backend/app/demo/mail_fixture.draft.json`: 40 emails (sender name and `.example` address, subject, body, label, `days_ago`, optional appointment placeholder rules), written in the main session; German private mail, English work mail.
- A loader and a one-off embedding script, as for the news fixture (`app/demo/news_fixture.py`, `embed_news_fixture.py`), embedding `"{subject}\n{body}"` per chunk exactly as `ingest/email/pipeline.py` does, rendered for a reference date.
- `backend/app/demo/mail_state.py`: emails and chunks for the demo mailbox, placeholders filled so the "this month" appointments fall in the reset day's month and the "next month" one in the next month; added to `BaseRows` (emails before chunks).

## Out of scope
- Labelling or embedding at reset; sending or replying.

## Acceptance criteria
- Given the demo user, when `/me` loads, then the agents are `documents`, `email`, `news`, `finance`; given the owner, the Email scope is the owner's mailboxes as before. (test)
- Given a reset on any day of a month (incl. the 1st and the last), then the three "this month" appointments and the moved appointment's new date fall in that month, the old date of the moved appointment is earlier than its new one, and the "next month" appointment falls in the next month. (test)
- Given a reset, then the demo mailbox holds 40 everyday emails with one chunk each and the fixture's labels, dates relative to today, no model calls. (test)
- Given a fixture whose embedding model or dimensions differ from settings, then loading refuses it. (test)
- Given the demo user after a reset, when they ask "Do I have any doctor's appointments this month?", then the answer lists the three appointments and the moved one at its new date, not next month's, with citations that open. (browser)
- Given the demo user, when they ask what they still need to reply to, then the answer cites the `needs_reply` work mail. (browser)

## Dependencies
Finance demo 003/03 (reset), 07-ai-news 001/05 (news fixture pattern).
