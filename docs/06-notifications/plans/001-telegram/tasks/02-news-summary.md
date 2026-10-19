# 001/02 — Big-news summaries

## Goal
A big-story message summarises what both newsletters said, with both links.

## Scope
- A structured model call (`NEWS_EXTRACTION_MODEL`, falling back to `OPENAI_CHAT_MODEL`) on the story's items' titles and blurbs: a headline and 2–3 sentences.
- Made once, when the story is detected; the text is stored in the row.
- On any model error: the first item's title and both links; error type logged.
- Content-free tracing as for the other model calls.

## Out of scope
- Rating importance; topics.

## Acceptance criteria
- Given a big story with a TLDR and an Alpha Signal item, when its row is created, then the text has the model's headline and summary and both urls. (test)
- Given a model error, when the row is created, then the text has the first title and both urls, and the error type is logged. (test)
- Given an existing row, when detection runs again, then the model is not called. (test)

## Dependencies
001/01.

## Notes
- Implementation plan: [02-news-summary.plan.md](02-news-summary.plan.md).

## Verified

2026-10-19, branch `feat/telegram-detection`.

- A big story's row has the model's headline and summary and both urls: `test_summary_text_has_headline_summary_and_both_links`, `test_new_big_story_is_summarised_once`. Pass.
- A model error falls back to the first title and both urls, and logs the error type: `test_model_error_falls_back_to_the_first_title`. Pass.
- An existing row never calls the model: `test_already_announced_story_never_calls_the_model`; neither does a disabled Telegram: `test_disabled_telegram_never_calls_the_model`. Pass.
- The model sees titles and blurbs only, no links: `test_the_prompt_sees_only_titles_and_blurbs`. Pass.
- Suite: `uv run pytest -m "not integration"`: 640 passed (`test_scheduled_rejects_limit_and_since` deselected). `ruff` is clean.
