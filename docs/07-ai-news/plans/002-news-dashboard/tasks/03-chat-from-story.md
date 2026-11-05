# 002/03 — Chat from a story

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
