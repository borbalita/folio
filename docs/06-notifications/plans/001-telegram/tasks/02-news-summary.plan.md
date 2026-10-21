# 001/02 — Big-news summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** A big-story message carries a model-written headline and 2–3 sentence summary of both newsletters, with both links; a model failure falls back to the first title.

**Architecture:** `app/notifications/summary.py` makes one structured call like newsletter extraction (`chat.completions.parse`, `NEWS_EXTRACTION_MODEL` or `OPENAI_CHAT_MODEL`, `NEWS_EXTRACTION_REASONING_EFFORT`). `NewNotification` carries the story's items for the pending news row; `record_notifications` replaces that row's text before inserting. Skipped rows (Telegram off, or already announced) never call the model.

**Spec:** [../README.md](../README.md), task [02-news-summary.md](02-news-summary.md).

## Tasks
- [ ] Tests: summary text; model error → fallback and logged type; no call when nothing new; no call when disabled. Implement. Commit.
