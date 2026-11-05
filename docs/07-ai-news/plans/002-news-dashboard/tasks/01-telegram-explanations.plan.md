# 002/01 — Telegram explanations: implementation plan

**Goal:** a big story's Telegram message explains the story in plain words, written from the whole newsletter text.

**Architecture:** `store.load_editions` reads `emails.body` for the story's email ids. `summary.news_text(items, editions)` puts the story's titles and each edition (once) in the prompt. The demo button loads editions the same way. The fallback adds the first item's blurb.

**Spec:** [../README.md](../README.md), task [01-telegram-explanations.md](01-telegram-explanations.md).

## Steps

- [ ] Tests first (`tests/notifications/test_summary.py`, `test_store.py`, `tests/demo/test_demo_news_telegram.py`): prompt holds each whole edition once and names the titles; fallback has headline, blurb, links, and no empty line without a blurb; `load_editions` maps email ids to bodies.
- [ ] Run them and see them fail.
- [ ] `summary.py`: new prompt, `summary_messages`/`request_summary`/`news_text` take `editions`.
- [ ] `detect.news_fallback_text`: first item's blurb as the body.
- [ ] `store.py`: `load_editions`, used when a pending story's text is written; `news_telegram.py` the same.
- [ ] Update `docs/06-notifications/overview.md` and the privacy page (text and "Last updated").
- [ ] Fast backend suite, ruff, `tsc`, lint; commit.
