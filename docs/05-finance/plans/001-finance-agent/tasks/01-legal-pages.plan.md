# 001/01 — Implementation plan

Docs only; no code or tests.

1. `docs/legal/privacy.md`: single-user personal project; reads N26, ING and PayPal account details and transactions through Enable Banking, and invoice emails; stored in Supabase; never shared or sold, never sent to tracing; consent at most 180 days, revocable at the bank or in the app; contact `borbala@tasnadi-ai.de` (given by the owner). It also names the processors that touch the data (Enable Banking, Supabase, Railway, OpenAI for invoice extraction), so "never shared" stays accurate.
2. `docs/legal/terms.md`: personal, non-commercial use; no warranty.
3. A Legal section in `docs/README.md` linking both. `legal/` is unnumbered on purpose: it belongs to no agent, and its URLs are registered with Enable Banking, so the path must stay fixed.
4. After merge: open both GitHub URLs (browser); the owner replaces the two URLs in the Enable Banking control panel and checks `GET /application` still returns `active: true` (manual).
