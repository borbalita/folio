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
- Given "pay them all from N26", when the turn runs, then drafts exist for the open invoices and the answer shows payment cards; no draft is approved. (test)
- Given a card id not returned by a tool this turn, when the answer is stored, then that card is dropped and logged. (test)
- Given an old answer whose invoice was paid since, when the thread is reopened, then the card shows it as paid. (browser)
- Given a payment card in chat, when the owner ticks and approves, then the QR shows as on the invoice page. (browser)

## Dependencies
001/10; the content-free tracing change.
