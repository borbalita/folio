# 001/10 — End-to-end run

**Goal**: `run --mode e2e --model <name>` runs the agent with real search and reports the same scores plus retrieval recall from its own tool calls.

**Why**: Tests whether the model's search decisions and answering work together.

**Scope**
- Reuse the 001/09 agent execution with the real `EmailRetriever`.
- Retrieval recall over emails returned across the agent's tool calls, from the step record; per-call results kept.
- Record tool arguments (query, dates, sender) so failures from wrong filters are visible.

**Out of scope**: scoring tool choice or filters as separate metrics.

**Likely areas affected**: `backend/evals/modes/e2e.py`, `backend/evals/scoring.py`.

**Acceptance criteria**: Luna and Sol runs appear in Langfuse with per-case scores, tool arguments, and retrieval recall.

**Test strategy**: Unit test recall across multiple tool calls; manual small paid run.

**Dependencies**: 001/09.

**Review notes**: Don't call cross-call recall "recall@10".

**Complexity**: Small.
