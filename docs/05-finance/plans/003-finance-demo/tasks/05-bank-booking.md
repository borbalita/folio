# 003/05 — Simulated bank booking

## Goal
An approved demo payment can be "booked" into the demo account, and the real matching marks its invoice paid.

## Scope
- `GET /finance/demo/payments`: the demo user's approved payments.
- `POST /finance/demo/payments/{id}/book`: write a booked debit (amount, payee, IBAN, reference, today) into the demo account, then run `match_for_user` for the demo user.

## Out of scope
- The presenter page (003/06).

## Acceptance criteria
- Given an approved payment, when it is booked, then a debit exists and the invoice is paid with an automatic link, and the payment is completed. (test)
- Given a payment that was already booked, when Book is called again, then nothing changes. (test)
- Given another user's payment id, when the demo user books it, then 404. (test)

## Dependencies
003/01.

## Notes
- Implementation plan: [05-bank-booking.plan.md](05-bank-booking.plan.md).
