# 002/05 — Web search in the News agent

Plan: [05-web-search.plan.md](05-web-search.plan.md)

## Goal
When the newsletters don't answer a question about a story, the News agent searches the web and cites what it finds, marked as coming from the web.

## Scope
- First step, done: check with a live call how PydanticAI 2.55's `WebSearchTool` exposes URL sources alongside `NewsAnswer` on the Responses API. See Live check.
- `WebSearchTool` on the News agent for non-demo users; demo accounts run without it.
- Instructions: newsletters first; search only for details they lack about a story or topic, never to browse general news; say which part came from the web. Replaces "answer only from tools" for web results; `insufficient_evidence` still applies when the web doesn't help either.
- A web citation as a second citation kind on news answers: storage (reviewed migration), grounding (its URL must be a search result or a page the model opened in this turn; otherwise that citation is removed and the answer kept), streaming, and the source panel (title, URL, "Open page").
- Raw citation markers in the model's text are stripped before it is stored or shown.
- Old threads and their item citations render as before.
- Privacy page: news questions may go to OpenAI's web search; update "Last updated".

## Out of scope
- Web search in other agents; fetching articles at ingest; web results on the dashboard.

## Acceptance criteria
- Given a web citation whose URL was neither a search result nor a page opened in this turn, when the turn ends, then that citation is removed and the answer kept. (test)
- Given a web citation to a page the model opened in this turn, when the turn ends, then it is kept. (test)
- Given a web citation whose URL differs from a source only by query string, fragment, scheme, a leading `www.`, host case or a trailing slash, when the turn ends, then it is kept. (test)
- Given a newsletter item citation no tool returned, when the turn ends, then grounding still rejects the answer. (test)
- Given an answer with raw citation markers, with or without private-use characters, when it is stored and shown, then the markers are gone. (test)
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
**Resolved 2026-11-06:** the live check below confirmed the facts, and the owner decided the grounding rule (spec, Approval state and Decisions). History:

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

2026-11-06, verified by the owner with PydanticAI 2.55 on the Responses API against gpt-6.1-sol. This settles the question above.

- **Enabling it:** `Agent(..., capabilities=[NativeTool(WebSearchTool())])`; the `native_tools=` kwarg doesn't exist. Model setting: `OpenAIResponsesModelSettings(openai_include_web_search_sources=True)`.
- **Parts:** `run.all_messages()` has `NativeToolCallPart` and `NativeToolReturnPart` named `web_search`. `call.args_as_dict()` is `{"type": "search", "queries": [...], "query": ...}` or `{"type": "open_page", "url": "..."}`. A return's `content` is `{"status", "sources": [{"type", "url"}]}`, with 0 sources for open_page. Other action types may exist and are ignored.
- **Opened pages are in the args,** so they can be grounded. The owner chose that a citation counts if it is a search result or an opened page, and that one matching neither is removed with the answer kept.
- **Structured output** comes back normally alongside those parts.
- **Markers:** `answer` can hold markers made of private-use characters; older runs showed them without those characters (`citeturn323873search4turn270125view0`). Both forms are stripped.
- **Cost:** each web turn used about 21k–38k input tokens.
- Streaming with this tool wasn't tested. The orchestrator doesn't use model streaming: see the plan.

## Verified
2026-11-07, fast tests and static checks only, with no app, database or live model calls. The migration `1b1a67f3980a` was hand-written and not applied. Not pushed, so no PR yet. Left unticked because the browser checks are open.

- A web citation matching neither a search result nor an opened page is removed and the answer kept (test): pass, `test_a_web_citation_this_turn_did_not_return_is_removed_and_the_answer_kept`, `test_an_answer_whose_only_citations_were_removed_is_kept`, `test_a_made_up_web_citation_is_removed_and_the_answer_kept`.
- A citation to a page opened this turn is kept (test): pass, `test_search_results_and_opened_pages_are_this_turns_urls`, `test_a_user_who_is_not_demo_gets_web_search_and_its_sources`.
- URLs compare by the owner's rule (test): pass, `test_urls_compare_ignoring_the_owners_differences`, `test_a_web_citation_with_a_noisy_url_is_kept`.
- An item citation no tool returned still fails the answer (test): pass, `test_an_unknown_item_citation_is_still_rejected_next_to_a_good_web_one`.
- Markers are gone, with or without private-use characters (test): pass, `test_citation_markers_are_stripped`, `test_markers_never_reach_the_stream_or_storage`.
- A web and an item citation, stored and read back, each have their own kind (test): pass, `test_web_and_item_citations_are_stored_and_read_back_with_their_own_kind`, `test_item_and_web_citations_are_stored_with_their_own_target`. Checked on what the backend streams and stores, with the database mocked. The frontend has no tests, so how they render is for the browser checks.
- A demo user's agent has no web search (test): pass, `test_a_demo_user_runs_with_no_web_search`, `test_turns_of_different_users_do_not_share_tools`.
- A stored thread with only item citations renders unchanged (test): pass, `test_a_stored_thread_with_only_item_citations_keeps_its_shape`. This checks that item citations keep the shape stored threads hold. Rendering an old thread is for the browser.
- A story thread's question the newsletters don't cover is answered from the web, and its citation opens the page (browser): **open**.
- "What were the big stories this week?" makes no web search (browser): **open**.
- A demo account says its newsletters don't cover it (browser): **open**.
- `/privacy` mentions web search under OpenAI, with the new date (browser): **open**. The source of `PrivacyPage.tsx` has the line and the date, 7 November 2026.
- Migration applied and `alembic check` clean on the test project: **open**, for the owner.
- Fast suite: 1197 passed, 4 deselected; ruff, tsc and eslint clean. Run with `unshare -rn` and loopback up, so nothing could leave the machine; see the plan's note on Langfuse.

2026-11-07, browser checks on the local app against the test Supabase project, signed in as the demo user, with live model calls. These replace the **open** lines above. Migration `1b1a67f3980a` applied to the test project and `uv run alembic check` found no drift.

The only test login is a demo user, which has no web search by design. So the first two checks ran the real backend from a throwaway wrapper that gave that user the web agent and counted each turn's web URLs. The demo check ran on the unmodified backend.

- A story thread's question the newsletters don't cover is answered from the web, and its citation opens the page (browser): pass. In the PHP story thread, "Which CVE numbers..." got an answer saying the newsletter doesn't name them and it checked PHP's site, with a `Web · php.net` citation. The panel showed "From the web" and "Open page". After a reload, the answer and citation were still there, with no leaked markers. The turn saw 43 web URLs. The cited URL was php.net's front page rather than a specific advisory.
- "What were the big stories this week?" makes no web search (browser): pass. Three big stories from the newsletters, with 0 web URLs.
- A demo account says its newsletters don't cover it (browser): pass. "Which banks are underwriting this IPO?" got "does not name the banks", with no web citation.
- `/privacy` mentions web search under OpenAI, with the new date (browser): pass. "Last updated: 7 November 2026".
- Not exercised live: the removal of a citation matching neither a source nor an opened page. That's covered by tests only.
- Finding, not part of this task: at phone width (375px) and in narrow windows the `/news` dashboard is hard to use. The thread sidebar takes most of the screen, story cards squeeze into a one-word column, and the Chat button overlaps the title. It comes from 002/02.
