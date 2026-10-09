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
