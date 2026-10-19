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
