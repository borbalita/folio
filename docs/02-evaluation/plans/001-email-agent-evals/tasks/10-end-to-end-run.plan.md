# 001/10 — End-to-end run: implementation plan

Task: [10-end-to-end-run.md](10-end-to-end-run.md).

## Approach

- `evals/modes/e2e.py`: the same agent execution as the answer test (`run_agent`), with a `RecordingRetriever` (an `EmailRetriever` that keeps every search: query, filters, and the emails returned, in order) in place of `ReplayRetriever`.
- Reranking is passed explicitly with `--rerank on|off`, as in the retrieval test, so every run says which (plan 002/03 compares both later).
- Scores: the answer test's `answer_scores`, plus `search_recall` in `evals/scoring.py`: the share of expected emails returned by at least one search in the run. Not called recall@10: it pools every call, so it can exceed what one search returns.
- `answer_scores` applies `grounding_pass` whenever the model saw evidence, not only when the case planned some, so an unanswerable end-to-end case is still checked when search returned emails. `distractor_cited` is passed only the distractors the agent actually saw, keeping its meaning ("when distractors were in the evidence").
- Summary, Langfuse scores, and the per-case print line reuse the answer test's helpers, adding `search_recall` and the number of searches.
- Tool arguments are already in each `ToolStep`; the per-call record adds the filters and returned email keys, and the `search_recall` comment lists each query with its filters.
- `run.py`: `--mode e2e`, needing `--model` and `--rerank`.

## Tests (first)

- `search_recall` across several calls: expected email found only in the second call; duplicates across calls; no expected email gives None; no searches gives 0.
- `RecordingRetriever` keeps each call's query, filters, and email keys in order.
- `answer_scores` checks grounding for an unanswerable case once the model saw evidence.

## Verification

- `uv run pytest -m "not integration"`.
- Paid run on v2 for Luna and Sol with rerank off; check Langfuse for per-case scores, tool arguments, and `search_recall`.
