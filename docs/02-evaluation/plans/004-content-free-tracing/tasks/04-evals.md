# 004/04 — Evals under content-free tracing

## Goal
Eval runs keep working under content-free tracing, can be run with full local content, and their docs say what Langfuse holds.

## Scope
- `eval_tracing()`: with `local_trace_content` on, skip the Langfuse key check and client and run in local mode.
- `run_experiment` in local mode: run the task over the committed local payloads, compute the same scores, write the report with `"published": false, "reason": "local_trace_content"`; the JSONL trace path is printed.
- The extraction mode refuses local-content runs with a message pointing to `--replay`.
- `evals/README.md`: the rule (app spans content-free; harness records may carry synthetic data and plan 003's newsletters), and how to run a case with local content.

## Out of scope
- Changing scores, datasets or the experiment records' content.

## Acceptance criteria
- Given `local_trace_content` on, when a retrieval run starts, then no Langfuse client is created and the report is written unpublished with the reason. (test)
- Given `local_trace_content` on, when an extraction run starts, then it exits non-zero with the refusal message. (test)
- Given the eval database and Langfuse keys, when a retrieval run runs normally, then the experiment and scores publish as before and the nested app spans carry no content. (manual)
- Given the eval database and `LOCAL_TRACE_CONTENT=true`, when a retrieval run runs, then the local report and a JSONL trace with queries and results are written. (manual)

## Dependencies
004/02.

## Notes
- Decisions: eval harness records keep their synthetic content; plan 003's datasets stay in Langfuse.
