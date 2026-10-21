# 003/07 — Production setup and rehearsal

## Goal
The demo works on `folio.tasnadi-ai.de`, and the owner has rehearsed it once.

## Scope
- The owner creates the demo user in Supabase and sets `DEMO_USER_ID` on Railway.
- First reset in production; one full rehearsal on laptop and phone.
- A short demo script in this task's Notes: what to show, in which order.

## Acceptance criteria
- Given `DEMO_USER_ID` in production, when the demo user logs in, then they see the base state and nothing of the owner's. (manual)
- Given the rehearsal, then a sent invoice appears within 30 s and the payment loop ends in paid. (manual)
- Given the rehearsal, the owner finds the demo presentable, and the measured time per new invoice is noted here. (manual)

## Dependencies
003/06.

## Notes
- Implementation plan: [07-rehearsal.plan.md](07-rehearsal.plan.md).

### Demo script (about 8 minutes)

**Before the call (5 minutes ahead)**
1. Laptop: sign in as the demo user on `folio.tasnadi-ai.de`, open Finance → Invoices. Close everything else in that browser window; this is the tab you share.
2. Phone: sign in as the demo user, open `folio.tasnadi-ai.de/finance/demo`.
3. Phone: **Reset demo** (confirm twice). The laptop list refreshes by itself within 5 s.
4. Check the list shows the base state: 5 rows with Open + Needs info.

**1. The problem (30 s, list on screen)**
- "Invoices arrive by email as PDFs, I bank with two banks, and nothing tells me what's still open. This agent does."

**2. The invoice list (1 min)**
- Point at the statuses: *overdue* (Eisenhalle), *due soon* (Wellenfunk, Havelwatt), *Needs info* (Nordhafen sent only a notice, the invoice sits in their portal: the agent doesn't guess), *Possible payment found* (Kaya & Brandt: same amount, but only the name matches, so it asks instead of deciding).
- Switch the filter to *Paid*: three *Matched automatically* (amount plus IBAN or reference), one *Paid before it arrived* (the PDF says it was debited).

**3. The live moment (2 min)**
- Phone: New invoice → *Normal* → Send. While it runs (about 10–20 s; measured time in Verified), explain: "The email is labelled, an invoice check decides whether there is something to pay, and a second model reads payee, IBAN, amount and reference from the PDF; IBAN checksums and plausibility checks guard it."
- The invoice appears in the list on its own. Open it: the PDF beside the extracted fields, editable.

**4. Paying (1 min)**
- *Pay* → the payment card shows payee, IBAN, amount, reference → *Approve* → the GiroCode. "I scan this in my banking app and confirm there; the app never moves money itself." Don't scan: the demo IBANs belong to no bank.
- The invoice now shows *Pending*.

**5. The bank booking (1 min)**
- Phone: Payments to book → *Book* ("as if the next bank sync brought the debit").
- Laptop: the invoice turns *Paid · Matched automatically*; open it to show why (same amount, IBAN, invoice number, payee).

**6. Optional: the Finance chat (1–2 min)**
- "What do I still need to pay?" → invoice cards. "Prepare payments for all of them" → payment cards; approving stays a button, never the chat.

**7. Optional: the other verdicts**
- Phone: New invoice → *Already paid* or *Online only*, and show where each lands.

**Talking points if asked**
- Bank access is read-only (PSD2 via Enable Banking); payments go through the bank's own app.
- Traces in Langfuse carry no content: models, tools, tokens, timings, errors.
- Everything here is fictional: vendors, IBANs (bank code 0, unpayable), the person.

**If something goes wrong**
- A live invoice takes long: keep talking through step 3; it shows within 30 s.
- Extraction fails or the check says "none": the invoice lands in *Needs info*. Show that as the point: it never guesses an amount.
- Anything odd: phone → Reset demo, and continue from step 2.

**After the call**
- Phone: Reset demo, so the next demo starts clean.

