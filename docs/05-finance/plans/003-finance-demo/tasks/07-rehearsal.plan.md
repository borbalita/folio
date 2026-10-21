# 003/07 Production setup and rehearsal — Plan

Manual task: no code. Steps in order, each with who does it.

1. **Owner:** set `DEMO_USER_ID` on the Railway backend service (the demo user's id, as in the local `.env`); wait for the redeploy.
2. **Claude, browser:** on `folio.tasnadi-ai.de`, signed in as the demo user: `/me` lists Documents and Finance, not Email or News.
3. **Claude, browser:** `POST /finance/demo/reset` from the page; Invoices, Transactions and Accounts show the base state and nothing of the owner's (criterion 1).
4. **Claude, with the owner's OK (real model calls):** send one invoice per kind through `POST /finance/demo/invoices`, note the time per invoice and where each lands; reset afterwards.
5. **After 003/06 is merged and deployed — owner and Claude:** one full rehearsal with the demo script (laptop shares the app, phone runs `/finance/demo`): a sent invoice appears within 30 s, Pay → Approve → Book ends in Paid (criterion 2); the owner judges it presentable (criterion 3).
6. **Claude:** Verified section with the measured times; tick 003/07 and set plan 003 Complete only if every criterion passed.
