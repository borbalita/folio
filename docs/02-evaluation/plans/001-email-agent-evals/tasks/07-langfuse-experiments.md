# 001/07 — Langfuse datasets and experiments

**Goal**: Case files are synced to Langfuse datasets, and the retrieval test runs as a Langfuse experiment with per-case scores.

**Why**: Gives the per-case run comparison UI that all later modes use.

**Scope**
- `sync`: upload `rag_cases.jsonl` and `label_cases.jsonl` to `email-rag-v1` and `email-labels-v1` with stable case IDs; rerunning is safe; changed content under an existing version is rejected.
- Experiment wrapper around `Langfuse.run_experiment`: one mode and one model or variant per run; run metadata (Git commit, mode, model or variant, data version, today, prompt and rubric hash); concurrency option, default 1.
- Move the retrieval mode onto the wrapper; local report still written; Langfuse failure keeps the local report and marks publication incomplete.
- Tag eval traces so they are distinguishable from app traffic.
- Eval entrypoints call the existing `configure_tracing()` at start and `shutdown_tracing()` in a `finally`, so agent and retrieval spans nest under experiment items and are flushed.
- From here on, the Langfuse-backed commands fail fast if Langfuse keys are missing.

**Out of scope**: annotation queues (001/12).

**Likely areas affected**: `backend/evals/langfuse_sync.py`, `backend/evals/experiment.py`, `backend/evals/run.py`.

**Acceptance criteria**
- After `sync`, both datasets exist in Langfuse with the expected item counts.
- A retrieval run appears as a dataset run with recall, precision, and MRR scores per item and a comparison URL.

**Test strategy**
- Verify `run_experiment` and dataset APIs against installed Langfuse 4.14.5 first.
- Unit: metadata building and sync diffing with a fake client.
- Manual: one run visible in the Langfuse UI.

**Dependencies**: 001/06.

**Review notes**: Never rerun model calls just to retry an upload.

**Complexity**: Medium.
