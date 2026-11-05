# 002/05 — Web search in the News agent

## Goal
When the newsletters don't answer a question about a story, the News agent searches the web and cites what it finds, marked as coming from the web.

## Scope
- First step: check with a live call how PydanticAI 2.55's `WebSearchTool` exposes URL sources alongside `NewsAnswer` on the Responses API. If sources can't be grounded, stop and raise it with the owner.
- `WebSearchTool` on the News agent for non-demo users; demo accounts run without it.
- Instructions: newsletters first; search only for details they lack about a story or topic, never to browse general news; say which part came from the web. Replaces "answer only from tools" for web results; `insufficient_evidence` still applies when the web doesn't help either.
- A web citation as a second citation kind on news answers: storage (reviewed migration), grounding (its URL must come from this turn's search results), streaming, and the source panel (title, URL, "Open page").
- Old threads and their item citations render as before.
- Privacy page: news questions may go to OpenAI's web search; update "Last updated".

## Out of scope
- Web search in other agents; fetching articles at ingest; web results on the dashboard.

## Acceptance criteria
- Given a web citation whose URL this turn's search didn't return, when the turn ends, then grounding rejects it. (test)
- Given a web citation and an item citation in one answer, when stored and read back, then both render with their own kind. (test)
- Given a demo user, when the agent is built, then it has no web search. (test)
- Given a stored thread with only item citations, when it is read, then it renders unchanged. (test)
- Given a story thread and a question the newsletters don't cover, when answered, then the answer says it came from the web and its citation opens the page. (browser)
- Given "What were the big stories this week?", when answered, then it makes no web search. (browser)
- Given a demo account, when it asks something its newsletters don't cover, then it says the newsletters don't cover it. (browser)
- Given the running app, when `/privacy` opens, then OpenAI's entry mentions web search and the date is updated. (browser)

## Dependencies
002/03.

## Blocked
2026-11-05, unattended run. Not implemented, and left unticked.

The task's first step is a live call to check how PydanticAI 2.55's `WebSearchTool` exposes URL sources alongside `NewsAnswer` on the Responses API, and the spec says to raise it with the owner before building if sources can't be grounded. This run was told to make no live model calls, so the check couldn't happen. The citation storage, grounding and source panel all depend on its answer, so building first would be a guess.

A read of the installed source, which doesn't replace the live check: `pydantic_ai/models/openai.py` has an `openai_include_web_search_sources` model setting, which asks the Responses API to include `web_search_call.action.sources`, and `_map_web_search_tool_call` turns a search call into tool call and return parts. So sources look reachable. How they arrive alongside structured output is still unconfirmed.

To unblock: run the live check, then implement on top of 002/03 (and 002/04's branch, to keep one alembic head).

All acceptance criteria are open: 4 (test), 4 (browser).
