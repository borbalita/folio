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

## Live check
2026-11-05, one live call, approved by the owner, with a public question on PydanticAI 2.55, the Responses API and `openai_include_web_search_sources`. Structured output came back as the expected type. Still blocked, now on the owner's decision below.

- **Sources are reachable.** Each search gives a `NativeToolCallPart` and a `NativeToolReturnPart` named `web_search`. The return's `content` is `{status, sources}`, and each source is `{type, url}`. The structured output and the sources arrive in the same run's messages.
- **A correct citation failed grounding.** The answer cited the release page `python.org/downloads/release/python-3152/`, which wasn't in the 16 sources, even with query strings ignored. The run made a second `web_search` call whose return had no `sources`. The likely explanation is that the model opened that page, with the URL in the call's args, but the check didn't print args, so that's unconfirmed. The spec's rule, "its URL must come from this turn's search results", would reject this answer.
- **Sources have no titles.** The source panel's title has to come from the model's citation.
- **Citation markers leak into the answer.** The `answer` text ended with raw markers (`citeturn323873search4turn270125view0`), which would show in the chat unless they're stripped.
- **URLs are noisy.** Sources carry query strings such as `?sid=` and `?trk=`, so comparing URLs needs a stated rule.
- Not checked: streaming, and how often a citation falls outside the sources (one run only). Token usage wasn't captured.

**Decision for the owner:** whether a URL the model opened in the same turn counts as a search result for grounding. Doing so needs one more live call to confirm the URL is in the call's args.
