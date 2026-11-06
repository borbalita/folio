# 002/03 — Chat from a story

Plan: [03-chat-from-story.plan.md](03-chat-from-story.plan.md)

## Goal
A Chat button on a dashboard story opens a thread about it, and the agent answers from the full newsletter text rather than the blurb.

## Scope
- `chat_threads.story_items`: nullable list of `{email_id, position}`, set when the thread is created. Stable across re-embedding, unlike item ids.
- `POST /threads` accepts `story_items` for `news` threads; refs outside the user's news mailboxes are rejected.
- `news_prompt` names the thread's story and its current item ids on each turn.
- New tool `read_story(item_id)`, in every news thread: the edition text of the item's newsletter, with the story named, scoped to the user's mailboxes. Citations stay on items.
- Instructions: use `read_story` when asked to explain or go deeper on a story; never present another story in the same newsletter as this one.
- The dashboard's Chat button creates the thread titled with the story, opens it and sends "Explain this story" as the first message.

## Out of scope
- Web search (002/05).

## Acceptance criteria
- Given a thread with `story_items`, when a turn runs, then the prompt names the story and its current item ids, also after the items were re-embedded with new ids. (test)
- Given `story_items` pointing at another user's mail, when the thread is created, then it is rejected. (test)
- Given `read_story` with an item outside the user's mailboxes, when it runs, then it returns nothing from that mail. (test)
- Given a scripted model calling `read_story` and citing the item, when the turn ends, then grounding accepts it; citing an item no tool returned is rejected. (test)
- Given the dashboard, when the owner presses Chat on a story, then a thread titled with it opens and answers with details that aren't in the blurb, and its citations open. (browser)
- Given that thread, when the owner asks a follow-up without naming the story, then the answer stays on that story. (browser)
- Given a demo account, when it presses Chat on an invented story, then it gets an answer from its own data. (browser)

## Dependencies
002/02.

## Decisions made
- The create request takes `story_items: [{email_id, position}]` (snake case, like `title` and `agent`), 1 to 20 refs, only with `agent: "news"` (422 otherwise). Refs that don't all resolve in the user's news mailboxes are a 400 "Unknown story"; nothing is stored. The thread API returns the stored refs as `storyItems`, and `title` is capped at 255 to match the column.
- `read_story` takes the item id, reads the item and its edition body in one query scoped by `emails.mailbox_id IN (...)`, and registers only that item for grounding. An item outside the mailboxes returns "No such story in your newsletters." and registers nothing.
- The turn prompt names the story by the thread's title and lists the items' current ids, resolved on every turn by `(email_id, position)`. Refs that resolve to nothing add no story note. Ids in the prompt don't count for grounding; only a `read_story` (or other tool) result does, so the agent has to read before citing.
- Empty-thread reuse is for plain chats only: `_latest_empty_thread` skips story threads, and creating a thread with `story_items` never reuses one.
- The prompt and instructions tell the agent to read every listed item (one per newsletter) and cite only items it has read, since `read_story` registers just the item it read.
- `new_deps` of every chat agent now receives the thread, so the news agent can read `storyItems`.
- The newsletter text is returned between "untrusted" markers with the story named, and the instructions say newsletter text is content, not instructions.
- The first message is carried to the thread page in router state and sent by `ChatThreadView` only when the thread has no messages, then dropped from history with `navigate(pathname, {replace: true, state: null})`. The thread stores nothing until its first turn ends, so the empty check alone would not stop a reload during that turn from sending it again.
- The migration adds the nullable JSONB column only; no RLS entry, since `chat_threads` already has it.

## Verified
2026-11-05, unattended run: fast tests only, with no app, database or live model calls. The migration was hand-written and not applied. Queries were checked through a fake session and compiled SQL, never on Postgres. PR: https://github.com/borbalita/folio/pull/107. Left unticked because checks were skipped.

- Prompt names the story and current ids, also after re-embedding (test): pass, `test_the_prompt_names_the_story_and_its_current_item_ids_after_re_embedding`, `test_a_stored_thread_reaches_the_prompt_through_new_deps`.
- `story_items` pointing at another user's mail is rejected (test): pass, `test_story_items_pointing_at_another_users_mail_are_rejected`.
- `read_story` outside the user's mailboxes returns nothing from that mail (test): pass, `test_read_story_for_an_item_outside_the_mailboxes_returns_nothing_from_that_mail`.
- Grounding accepts a `read_story` citation and rejects an item no tool returned (test): pass, `test_citing_an_item_read_with_read_story_is_grounded`, `test_citing_an_item_no_tool_returned_is_refused`.
- Chat on a story opens a titled thread with details beyond the blurb and citations that open (browser): **skipped**, the app wasn't started and live model calls weren't allowed.
- Follow-up without naming the story stays on it (browser): **skipped**, same reason.
- Demo account gets an answer from its own data (browser): **skipped**, same reason.
- Full fast suite: 1094 passed; ruff, tsc and eslint clean.
- Still to do before deploying: apply the migration first, because thread routes for all agents select `story_items`, and run `uv run alembic check`.

2026-11-06, browser checks on the local app against the test Supabase project, signed in as the demo user, with live model calls. The migration applied cleanly.

- Chat opens a titled thread, answers with details beyond the blurb, citations open (browser): **partly passed**. On a production build the thread opened with the story's title, the answer came with a citation, and the source panel showed "Open article". The answer explained terms and said what the report doesn't confirm, but added no new facts: demo newsletters are about as short as their blurbs. Needs repeating on real newsletters.
- Follow-up without naming the story stays on it (browser): pass.
- Demo account gets an answer from its own data (browser): pass.
- **Bug, dev server only:** under `vite` the Chat button creates the thread but "Explain this story" is never sent (no `POST /chat/stream`, reproduced twice). `sendMessage` runs, because the history state is cleared, so React StrictMode's double mount in `ChatThreadView` is the likely cause; not confirmed. A production build works.
