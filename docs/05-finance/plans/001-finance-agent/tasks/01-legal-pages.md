# 001/01 — Privacy and terms pages for Enable Banking

## Goal
Replace the placeholder privacy and terms URLs of the Enable Banking application with real pages in the public repository.

## Scope
- `docs/legal/privacy.md`: a single-user personal project; which data it reads (account details and transactions of N26, ING and PayPal through Enable Banking; invoice emails); where it is stored (Supabase), that it is never shared or sold and never sent to tracing; consent lasts at most 180 days and can be revoked at the bank or in the app; a contact email.
- `docs/legal/terms.md`: personal, non-commercial use, no warranty.
- Link both from `docs/README.md`.

## Out of scope
- Pages in the frontend.

## Acceptance criteria
- Given the merged pages, when `https://github.com/borbalita/folio/blob/main/docs/legal/privacy.md` and `.../terms.md` are opened, then both render. (browser)
- Given the Enable Banking control panel, when the owner replaces both URLs of the Portfolio application, then `GET /application` still returns `active: true`. (manual)

## Dependencies
None.

## Notes
- Follows up the placeholder noted in Open questions.
- Implementation plan: [01-legal-pages.plan.md](01-legal-pages.plan.md).
