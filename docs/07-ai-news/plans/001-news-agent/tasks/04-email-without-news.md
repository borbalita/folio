# 001/04 — News moves out of the Email agent

## Goal
The Email agent answers about mail only and points news questions to the News agent.

## Scope
- Remove `search_news`, `list_big_news` and the news deps from the Email agent; its instructions answer AI-news questions with a one-line pointer to the News agent, without searching or citing.
- Picker description: "Search your mail, with citations to each message."
- The eval modes `answer.py` and `e2e.py` stop passing a news retriever.
- Old Email threads with news citations still render.

## Acceptance criteria
- Given a news question, when the Email agent answers, then it calls no tool and points to the News agent. (test)
- Given an old Email thread with news citations, when it opens, then the citations still show. (browser)
- Given the Email evals, when their modes are built, then they run without the news retriever. (test)

## Dependencies
001/02.
