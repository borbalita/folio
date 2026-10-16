# 001/12 — Finance chat with cards

## Goal
The owner asks Finance about invoices and prepares payments in chat, and answers show live invoice and payment cards.

## Scope
- The Finance agent (a sibling of the email agent) with tools: list invoices, get one invoice, search transactions, prepare payments (drafts only), list accounts. No tool approves.
- Structured answers with cards that reference invoices or drafts by id; ids must come from this turn's tool results; cards stored per message and rendered from current data with the components of 001/06 and 001/10.
- Instructions: dates in Europe/Berlin; amounts only from tools; for "pay" requests prepare drafts and say they await approval.
- Content-free tracing.

## Out of scope
- Spending questions (plan 002).

## Acceptance criteria
- Given open invoices, when the owner asks what is still to pay, then the answer shows an invoice card with them. (test)
- Given "pay them all", when the turn runs, then drafts exist for the open invoices and the answer shows payment cards; no draft is approved. (test)
- Given a card id not returned by a tool this turn, when the answer is stored, then that card is dropped and logged. (test)
- Given an old answer whose invoice was paid since, when the thread is reopened, then the card shows it as paid. (browser)
- Given a payment card in chat, when the owner ticks and approves, then the QR shows as on the invoice page. (browser)

## Dependencies
001/10; content-free tracing ([eval plan 004](../../../../02-evaluation/plans/004-content-free-tracing/README.md), tasks 01–03).

## Notes
- "Pay them all" names no account: the QR code carries none (owner's decision, 2026-10-16, PR #35).
- Implementation plan: [12-finance-chat.plan.md](12-finance-chat.plan.md).

## Verified

2026-10-16, branch `feat/finance-chat`, local app (http, built-in browser) against the real database.

- Open invoices are answered with an invoice card: `test_open_invoices_answer_shows_an_invoice_card`. Pass. In the browser, "What do I still need to pay?" answered "1 open invoice, 2 need info", with a card listing the open Praxis invoice (€45.00, overdue) and the two needs_info Vodafone bills, plus Pay selected.
- "Pay them all" creates drafts for the open invoices and shows payment cards; no draft is approved: `test_pay_them_all_creates_drafts_and_payment_cards_none_approved`. Pass. In the browser the only open invoice already had an approved payment (the QR scanned for 001/10). With the fix below, the answer said no new payment was prepared and why, and the database still holds that one approved draft.
- A card id not returned by a tool this turn is dropped and logged: `test_unknown_card_id_is_dropped_and_logged`. Pass.
- An old answer whose invoice was paid since shows it as paid on reopening (browser): **pending.** The card loads current data, so it will show the Praxis invoice as paid once the bank sync matches the 001/10 payment; check then.
- Ticking and approving a payment card in chat shows the QR (browser): **not checked.** No invoice could be paid: the only open one already has an approved payment. The chat card is the same `PaymentCard` as on the Payments page, where approving shows the QR (001/10, verified).
- Suite: `uv run pytest -m "not integration"`: 617 passed with the real `.env` (`test_scheduled_rejects_limit_and_since` deselected; it hangs on a live Langfuse flush). `ruff`, `tsc` and `lint` are clean.

Found during verification:
- "Pay them all" a second time cancelled an already approved payment and made a new QR code, though the first may have been paid (behaviour from 001/10). Fixed here at the owner's request: an invoice with an approved payment is skipped as `already_approved`, and only unapproved drafts are replaced.
- An English question got a German answer, taken from the German invoices. The instructions now say to answer in the language of the owner's message.

Deferred from the final review: `get_invoice` omits the match state; the trace's card count includes dropped cards; cards reload a few times while a reply streams; a payments card shows "no longer available" for any loading error; the expiry banner sits flush in chat and the thread list is cramped on phones; finance chats can't be renamed or deleted; the transaction search doesn't escape `%` and `_`. Spec wording waiting for the owner: success criterion 5 should say "nothing can be approved by the assistant", and this task's "ticks and approves" predates dropping the tick.
