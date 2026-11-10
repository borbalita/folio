# 002/03 — Chat from a story: implementation plan

Task: [03-chat-from-story.md](03-chat-from-story.md). Spec: [README](../README.md), Design.

- **Column:** `chat_threads.story_items` (JSONB, nullable), list of `{email_id, position}`. Hand-written migration chained from `4d8e2a7f9b13`. No new table, so no RLS entry.
- **Queries:** `app/database/news_story.py`, every statement scoped by `emails.mailbox_id IN (...)` in the query itself. `read_story(mailbox_ids, item_id)` returns the item and its edition body; `thread_story(mailbox_ids, refs)` resolves refs to the items' current ids by `(email_id, position)`; `owns_all(mailbox_ids, refs)` checks refs at thread creation.
- **Create route:** `CreateThreadRequest.story_items`; only for `news`, each ref must resolve in the user's mailboxes or the request is a 400. `chats` stores and returns it (`storyItems`).
- **Turn:** `new_deps` gets the thread; `NewsAgentDeps.story_items` and `story_title`. `run_news_agent` resolves the current items and `news_prompt` names the story and ids.
- **Tool:** `read_story(item_id)` registered on the news agent; remembers the item so a citation of it is grounded. Text is framed as untrusted newsletter text with the story named.
- **Instructions:** use `read_story` to explain or go deeper; never present another story in the same newsletter as this one.
- **Frontend:** `api.createThread` takes story items; Chat button on the card; the dashboard creates the thread, navigates with `firstMessage` in router state, and `ChatThreadView` sends it once when the thread has no messages.

Tests (red first): `tests/database/test_news_story.py` (SQL scope and keys), `tests/news_assistant/test_read_story.py` (scoping with a filter-honouring fake session; scripted-model grounding; prompt), `tests/api/test_story_threads.py` (rejection).
