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

## Notes
- Implementation plan: [03-sender.plan.md](03-sender.plan.md).

## Verified

2026-10-19, branch `feat/telegram-detection`.

- Pending rows go out oldest first and become `sent` with `sent_at`: `test_pending_rows_are_sent_oldest_first`. Pass.
- 21:59 sends, 22:00 holds, 06:59 holds, 07:00 sends (Berlin): `test_quiet_hours`. Pass.
- A 429 or 5xx keeps the row pending with one more attempt, and the fifth makes it `failed`: `test_retryable_answer_keeps_the_row_pending_until_five_attempts`, `test_network_error_counts_an_attempt`. Pass.
- A 401 fails the row, logs `telegram_misconfigured` without the text, and stops the run: `test_bad_token_fails_the_row_and_stops`. Pass.
- Also: Telegram off sends nothing (`test_off_sends_nothing`); the bot token, which is part of the request URL, is redacted from httpx's request log (`test_the_token_never_reaches_the_logs`). Found while building: httpx logs every URL at INFO, so without the filter the token would reach Railway's logs.
