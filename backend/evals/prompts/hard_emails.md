You add hard labelling cases to an existing synthetic mailbox that tests an email assistant. The mailbox owner is {owner_name} <{owner_address}>, living in Berlin; today is {today}. The existing senders, emails, and unanswerable topics are listed in the user message.

Plan {per_label} new email(s) for each label below. Every new email must be genuinely hard to label: its surface cues (sender type, subject, layout, wording) point to a different label than the correct one, and only a careful reading settles it. The `label` field is the correct label under these definitions:

{labels}

Ideas, not a checklist: a person's question buried at the end of a long club bulletin; a friend asking to be paid back for concert tickets; a "your account update" message that is really a sales pitch; an informational digest that mentions many products without selling them; an automated "do not reply" notice that still asks something.

Rules:

- Each new email gets exactly one trap, of kind `borderline_label`, with `related_keys` empty and a `note` naming the tempting wrong label and why the correct one wins.
- Keys continue from `{next_key}` upwards. Reuse existing senders where it fits; new senders get new `s_` keys and addresses on domains ending in `.example`.
- Send every email within the {history_days} days before today, with the correct Europe/Berlin UTC offset.
- Facts follow the existing style (written-out dates, exact amounts) and must not repeat any existing email's fact values.
- Do not touch any unanswerable topic: no new email may answer or relate to one.
- A `brief` says only what the sender would write. Never explain what the email is not.
- `in_reply_to` is null.
