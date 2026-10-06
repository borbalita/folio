# 001/09 — Answer test with fixed evidence

**Goal**: `run --mode answer --model <name>` runs the real agent on preset evidence and scores refusals, cited evidence, and grounding.

**Why**: Isolates answering skill from search, and is the core of the model benchmark.

**Scope**
- `ReplayRetriever`: same interface as `EmailRetriever.search`; ignores the query; returns the case's expected chunks (plus distractor, or nothing) loaded from the eval database.
- Agent execution: call the cached agent directly with `email_prompt(question, today=case.today)`, fresh `EmailAgentDeps` per case with the replay retriever, and `model=` per run.
- Step record from the PydanticAI message history: tool calls, arguments, results, final `EmailAnswer`.
- Code scores: `refusal_correct` (with `wrong_refusal` / `missing_refusal` outcome), `evidence_cited`, `grounding_pass` via `EmailGrounder`.
- Runs as a Langfuse experiment through the 001/07 wrapper.

**Out of scope**: judge scores (001/11).

**Likely areas affected**: `backend/evals/modes/answer.py`, `backend/evals/replay.py`, `backend/evals/agent_run.py`, `backend/evals/scoring.py`.

**Acceptance criteria**
- A run with Luna and a run with Sol each appear in Langfuse with per-case scores and the recorded steps.
- Unanswerable cases with no evidence are scored on refusal only.

**Test strategy**
- Verify per-run `model=` override and message-history APIs in PydanticAI 2.46 first.
- Unit: replay retriever, score functions, step extraction from a recorded message history; agent run with PydanticAI's test model.
- Manual: one small paid run per model.

**Dependencies**: 001/07, 001/08.

**Review notes**: No production code changes beyond 001/08. Grade the model's own answer, not the grounder's canned reply.

**Complexity**: Medium.
