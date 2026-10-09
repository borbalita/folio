You design a synthetic mailbox for testing an email assistant. Write the plan as structured data; another step turns each planned email into a real message.

## The mailbox owner

{owner_name} <{owner_address}> lives in Berlin and works as a product designer. Mail is in English. Money is mostly in euros. Today is {today}; every email was sent in the {history_days} days before today, with timestamps in Europe/Berlin local time and the correct UTC offset for that date (+02:00 in summer time, +01:00 after the last Sunday of October).

## Senders

Invent fictional people and organisations: a landlord, utilities, a phone and internet provider, a dentist, a bank, colleagues, friends and family, a sports club, shops, an airline, a city office, informational mailing lists, and so on. Every address must be on a domain ending in `.example` (e.g. `billing@stromwerk.example`). No AI or machine-learning newsletters.

## Labels

Plan {per_label} emails (±1) for each label below. These are the labels the email *should* get:

{labels}

## Briefs

A `brief` says only what the sender would write, as the sender sees it. Never contrast the email with other emails, unanswerable topics, or labels ("this is not a water bill", "no booking was made"): real senders don't explain what their mail is not, and the test must not hand the assistant its answer. Why an email is tricky belongs only in its trap `note`.

## Facts

Each email has one to four facts: concrete details a question could ask about (amounts, due dates, appointment times, order or invoice numbers, places, names). Write each `value` exactly as it should appear in the email text, e.g. `€1,240.00`, `14 October 2026`, `10:30`, `INV-20931`. Use written-out dates like `14 October 2026`, not `14/10`. Outside near-duplicate pairs, keep facts distinctive so a question about one email has one right answer.

## Traps

Mark traps on the emails they apply to. Include at least:

- {min_near_duplicate} `near_duplicate` traps: emails that look almost the same as another email (same sender and kind of subject) but differ in a key fact, e.g. the September and October electricity invoice with different amounts, or a meeting moved to a new time. Put the other email's key in `related_keys`, on both emails.
- {min_date_boundary} `date_boundary` traps: emails sent within two hours of local midnight at the start or end of a month or week, so a date-range question must place them correctly.
- {min_borderline_label} `borderline_label` traps: emails that could plausibly get another label (a receipt that looks like an invoice but is already paid, a newsletter with a small promotion, a notice that hides one question). The `label` field is the correct one; the note says why.

Also plan a few replies: set `in_reply_to` to the key of the email being answered (the reply comes later and usually has the same subject with `Re:`).

## Unanswerable topics

Plan at least {min_unanswerable} topics Anna might plausibly ask about that no email answers, e.g. a water bill when only electricity bills exist, or a flight to a city she never booked. Where an email looks related but does not answer, list it in `near_miss_keys`.

## Keys

Emails are `e01`, `e02`, ... in order of `sent_at`. Senders are `s_` plus a short name. Topics are `u01`, `u02`, ...
