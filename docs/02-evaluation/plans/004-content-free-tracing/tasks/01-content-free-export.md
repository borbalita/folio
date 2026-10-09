# 004/01 — Content-free Langfuse export

## Goal
No app trace in Langfuse carries content; traces keep models, tools, tokens, timings, counts and error types.

## Scope
- `Agent.instrument_all(InstrumentationSettings(include_content=False, include_binary_content=False))`.
- Hand-made spans lose their content: `generate-chat-response` (no input or output), `hybrid-search` and `news-search` (no input), `embed-query` (no input), `rerank` (no input or output; counts move to metadata). Their metadata, levels and status codes stay.
- `ContentFreeExporter` around an `OTLPSpanExporter` built as the Langfuse SDK builds it, passed as `Langfuse(span_exporter=...)`: keeps allowlisted attribute keys only, reduces `exception` events to `exception.type`, drops other events, replaces the status description with the exception type.
- The allowlist as concrete keys, taken from real content-free spans of a document turn, an email turn, a failing turn and a title run.
- Delete the email regex and `_mask_otel_spans`.
- Update `docs/02-evaluation/legacy/evals-todo.md` Steps 3 and 5: trace input and output are content-free, so scores and counts are the signal.

## Out of scope
- Local trace content and the guard (004/02); ingest (004/03); evals (004/04).

## Acceptance criteria
- Given a document turn and an email turn through an in-memory exporter wrapped in `ContentFreeExporter`, when spans are exported, then no attribute or event contains the user text, answer, query, filter values, passage text or tool result, and model, token counts, tool names and `citation_count` are present. (test)
- Given a turn whose agent raises with a message containing the user text, when spans are exported, then the level and exception type are present and the message appears nowhere, including events and status. (test)
- Given an agent run with a PDF as input, when spans are exported, then no attribute holds binary or base64 data. (test)
- Given a span with an attribute key not on the allowlist, when exported, then that key is absent. (test)
- Given the app running locally with Langfuse keys, when one Documents and one Email turn run, then Langfuse shows the nested spans with models, tokens and tool names and no content. (manual)

## Dependencies
None.

## Notes
- Decisions: all agents; allowlist, not masking; filters and exception messages are content.
- Langfuse 4.14.5's `mask_otel_spans` cannot touch events or status, hence the exporter.
- Harness spans `experiment-item-run` and `experiment-item-task` pass the exporter unchanged.
- Implementation plan: [01-content-free-export.plan.md](01-content-free-export.plan.md).

## Verified

2026-10-09, PR: not opened yet.

- Document and email turns export no content; model, tokens, tool names and `citation_count` present (test): met compositionally, not by one test of the real agents, whose tools need the database. `tests/test_observability.py` runs a PydanticAI agent with a tool, a PDF and instructions through `ContentFreeExporter`; the source-layer tests in `tests/chat/test_orchestrator.py`, `tests/retrieval/test_base.py`, `tests/retrieval/news/test_news_retriever.py` and `tests/retrieval/email/test_email_rerank.py` cover every hand-made span; `tests/test_trace_export.py` covers the exporter. Passed.
- A raising turn exports level and exception type, no message (test): `test_failing_agent_exports_the_type_only`, `test_failed_turn_span_keeps_the_code_not_the_message`, `test_exception_events_keep_only_the_type`, `test_status_message_gives_way_to_the_exception_type`. Passed.
- A PDF input leaves no binary or base64 attribute (test): `test_agent_run_records_no_content_or_file_at_the_source`, which fails when content and binary are switched on. Passed.
- Unknown attribute keys are dropped (test): `test_unknown_keys_are_dropped`; library drift is caught by `test_recorded_keys_match_the_known_set`. Passed.
- One Documents and one Email turn in Langfuse show shape and no content (manual): pending; needs the owner to run the turns and look in Langfuse.

Fast suite: 413 passed; `ruff check` clean. A fresh whole-branch review found no critical issues; its four important findings were fixed with tests.
