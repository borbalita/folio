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

## Notes
- Implementation plan: [01-telegram-explanations.plan.md](01-telegram-explanations.plan.md).

## Decisions made
- The editions travel as a separate `dict[email_id, body]` argument to `news_text`, not a new field on `NewsItemFacts`, so the facts used by detection stay small and the body is loaded only for stories that will be summarised.
- `news_fallback_text` also feeds the placeholder text of pending rows before the summary replaces it, so those placeholders now carry the blurb too. Two `test_detect.py` expectations changed to match.
- Each edition is labelled with its newsletter name in the prompt; a story's items in one newsletter include that edition once.
- Privacy page: the Telegram line now reads "big AI news headlines with short explanations"; date set to 5 November 2026.
- Overview: the sentence "Messages never contain ... email text" was narrowed to invoice messages, since news messages now paraphrase newsletter text.

## Verified
2026-11-05, unattended run: fast tests only, with no app, database, Telegram or live model calls. PR: https://github.com/borbalita/folio/pull/105. Left unticked because checks were skipped.

- Whole newsletter text and story titles in the messages (test): pass, `test_the_prompt_has_each_whole_newsletter_and_names_the_titles`.
- Each edition appears once (test): pass, `test_two_items_in_one_newsletter_include_that_edition_once`.
- Failed or unparsable call has headline, blurb and links (test): pass, `test_failed_call_keeps_the_blurb_when_there_is_one`, `test_any_model_error_falls_back`.
- Empty blurb leaves no empty line (test): pass, `test_failed_call_with_an_empty_blurb_has_no_empty_line`.
- Owner reads at least three explanations of real stories (manual): **skipped**, needs the database, live model calls and the owner.
- Presenter's button sends the new form (manual): **skipped**, needs the running app and Telegram.
- `/privacy` shows the updated line and date (browser): **skipped**, the app wasn't started. The source of `PrivacyPage.tsx` has the new line and date.
- Full fast suite: 1046 passed; ruff, tsc and eslint clean.
