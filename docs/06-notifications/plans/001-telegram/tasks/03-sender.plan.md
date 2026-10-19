# 001/03 — Telegram sender Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** `send_pending(session, now, client=None) -> dict[str, int]` delivers pending rows to the owner's chat, oldest first, never during quiet hours, retrying failures on later runs.

**Architecture:** `app/notifications/telegram.py`. Synchronous `httpx.Client` (ingest is synchronous), `POST https://api.telegram.org/bot<token>/sendMessage` with `chat_id` and `text`, 10 s timeout, one message a second at most. Each row is committed on its own, so a crash mid-run loses no state.

**Spec:** [../README.md](../README.md), task [03-sender.md](03-sender.md).

## Global Constraints
- Quiet hours: Berlin local time `22:00 <= t` or `t < 07:00` → nothing sent, counts `held`.
- 200 → `sent`, `sent_at = now`. 429, 5xx or `httpx.HTTPError` → `attempts + 1`, `last_error` = status or error type; at 5 attempts → `failed`. Other 4xx → `failed`, `telegram_misconfigured` logged, and the run stops (the rest stay pending).
- Telegram off (settings missing) → nothing sent.
- Logs and `last_error` never hold the text or Telegram's answer body.

## Tasks
- [ ] Tests for the four `(test)` criteria plus "off sends nothing"; implement; commit.
