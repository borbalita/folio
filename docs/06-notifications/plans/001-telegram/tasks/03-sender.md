# 001/03 — Telegram sender with quiet hours and retries

## Goal
Pending notifications reach the owner's Telegram chat, never at night, and failures are retried and visible.

## Scope
- `sendMessage` through `httpx` (10 s timeout), pending rows oldest first, one at a time.
- Quiet hours 22:00–07:00 Europe/Berlin: nothing sent.
- `429`, `5xx` or network error: attempt counted, row stays pending; 5 attempts: `failed`. Other `4xx`: `failed` at once, `telegram_misconfigured` logged.
- Logs and `last_error` hold error types only.

## Out of scope
- Receiving messages.

## Acceptance criteria
- Given pending rows and Telegram answering 200, when the sender runs, then they are `sent` with `sent_at`, oldest first. (test)
- Given 21:59, 22:00, 06:59 and 07:00 Berlin, when the sender runs, then it sends, holds, holds, sends. (test)
- Given a `429` or `5xx`, when the sender runs, then the row stays pending with one more attempt; after 5, it is `failed`. (test)
- Given a `401`, when the sender runs, then the row is `failed` and `telegram_misconfigured` is logged. (test)

## Dependencies
001/01.
