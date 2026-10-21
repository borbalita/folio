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
