# 002/01 — Telegram explanations

## Goal
A big story's Telegram message explains the story in plain words, so the owner understands it without opening a link.

## Scope
- `summary.py`: the call reads the whole newsletter (`emails.body`) of each of the story's items, with the story's titles named as the focus, and returns a headline and a plain explanation long enough to understand the story without opening the links: what happened, terms explained, why it matters. No fixed sentence count, and not a long briefing. Facts about the event come only from the newsletters; plain-word definitions and why it matters may go beyond them.
- `store.py` and `app/demo/news_telegram.py`: load the edition text for the call.
- Fallback: the first headline, its blurb when there is one, and the links.
- Update [06-notifications overview](../../../../06-notifications/overview.md): the news row, the summarise step, and that news messages paraphrase newsletter text.
- Privacy page: the Telegram line changes from big AI news headlines to headlines and explanations; update "Last updated".

## Out of scope
- Storing explanations (002/02); security alerts (002/04).

## Acceptance criteria
- Given a big story, when the summary messages are built, then they contain each item's whole newsletter text and name the story's titles. (test)
- Given a story whose items are in one newsletter of two, when messages are built, then each edition appears once. (test)
- Given a failed or unparsable model call, when the message is built, then it has the first headline, its blurb and the links. (test)
- Given a failed call on an item with an empty blurb, when the message is built, then it has the headline and links and no empty line. (test)
- Given the real stories behind the last 12 sent messages, when explanations are generated without sending, then the owner reads at least three and agrees they are clear, say why the story matters, and don't mix in other stories. (manual)
- Given a demo account, when the presenter's button is pressed, then the owner's Telegram gets the new form for a demo story. (manual)
- Given the running app, when `/privacy` opens, then the Telegram line and the date are updated. (browser)

## Dependencies
None.
