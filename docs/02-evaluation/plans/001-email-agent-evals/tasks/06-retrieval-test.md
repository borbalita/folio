# 001/06 — Retrieval test

**Goal**: `run --mode retrieval` reports recall@10, precision@10, and MRR per case and overall, in a local report.

**Why**: First end-to-end slice of the harness; measures search independently of the chat model.

**Scope**
- `evals/run.py` entrypoint with `--mode` and the localhost guard.
- Retrieval mode: for each case, call `EmailRetriever().search` with the probe query and filters as user A; group chunks by email keeping first rank; map to scenario keys.
- `scoring.py`: recall@k, precision@k, MRR; unanswerable cases excluded from recall and counted.
- Local JSON report in a gitignored directory, plus a short console summary.

**Out of scope**: Langfuse (001/07).

**Likely areas affected**: `backend/evals/run.py`, `backend/evals/modes/retrieval.py`, `backend/evals/scoring.py`.

**Acceptance criteria**
- The command runs all RAG cases and writes a report with per-case results and averages.
- Unanswerable cases appear with recall "not applicable".

**Test strategy**: Unit tests for metric arithmetic, including no expected emails, no results, duplicates across chunks, and first-rank grouping.

**Dependencies**: 001/05.

**Review notes**: Metrics are at email level, not chunk level.

**Complexity**: Small.
