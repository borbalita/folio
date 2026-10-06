You make an existing synthetic mailbox harder to search. The mailbox owner is {owner_name} <{owner_address}>, living in Berlin; today is {today}. The existing senders, emails, unanswerable topics, and planned questions are in the user message. An assistant will answer the owner's questions by searching this mail, and the test must show when search finds the wrong emails or misses some.

Add about {new_emails} new emails and the questions they make possible. The labels the new emails should get (spread them roughly evenly):

{labels}

## Story lines

Plan {story_lines} story lines of two to four linked emails each, where the information a person would ask about is scattered: an invoice, then a correction, then a payment reminder; a meeting proposed, moved, and moved again; an order, a partial shipment, a second shipment; a landlord notice and a follow-up with the date. Later emails in a line set `in_reply_to` to an earlier email of the same line (only new emails). When a value changes, give the fact the same `name` in both emails and different `value`s.

## Look-alikes and filler

The rest are emails on topics the mailbox already has, written so they compete in search: other utilities and providers with invoices and similar amounts, other people proposing meetings, other shops with order numbers, other club mailings. Different senders, similar vocabulary. They must not change, correct, or contradict anything in an existing email.

## Planned questions

Write questions that only the scenario facts answer. Each `answer_facts` entry points to a fact by email key and fact name; an answer may use existing emails as well as new ones. Questions ask for stated facts only, never arithmetic or totals. At least:

- {min_multi_email} `multi_email`: the answer needs facts from two to four different emails.
- {min_superseded} `superseded`: within one of your story lines, a later new email changes a value from an earlier new email (same fact `name`, different `value`). Ask for the current value; `answer_facts` points to the later email and `distractor_keys` includes the earlier one. Never supersede an existing email's value.
- {min_vague} `vague`: the person refers to people by role ("my landlord", "the dentist") and time loosely ("last month", "recently"); the answer can be in one or several emails, and look-alike senders exist.
- {min_unanswerable} `unanswerable`: near misses, e.g. a month or provider the mailbox does not have while similar emails exist; list those look-alikes in `distractor_keys`.

`ask` says what the person wants to know and how they refer to people and time. Put look-alike emails that could be mistaken for the answer in `distractor_keys`.

## Rules

- Keys continue from `{next_key}` for emails and `q{next_question}` for questions. Reuse existing senders where it fits; new senders get new `s_` keys and addresses on domains ending in `.example`.
- Every email is sent within the {history_days} days before today, with the correct Europe/Berlin UTC offset.
- Facts use the existing style (written-out dates, exact amounts) and must not repeat any existing email's fact values.
- New emails have no traps (`traps` is empty).
- A `brief` says only what the sender would write; never explain what the email is not.
