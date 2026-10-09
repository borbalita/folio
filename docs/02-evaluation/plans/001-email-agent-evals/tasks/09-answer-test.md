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

## Verified

2026-10-07, on data v2 (49 cases, 13 unanswerable), both models through the Responses API at default effort:

- Luna and Sol runs in Langfuse with per-case scores and recorded steps: passed ([Luna run](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/8383dbf0-d9f8-461e-a909-22fea3b60ea2), [Sol run](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/10aaea12-4e30-4feb-a833-36dfc32d0b61)).
- Unanswerable cases with no evidence are scored on refusal only: passed (unit test, and no evidence or grounding score on those items in both runs).
- Per-run `model=` override and message history checked against PydanticAI 2.46 before building; agent run covered by a `FunctionModel` unit test.

| | Luna 6 | Sol 6.1 |
| --- | --- | --- |
| refusal_correct | 49/49 | 49/49 |
| evidence_cited | 35/36 | 36/36 |
| grounding_pass | 49/49 | 49/49 |
| distractor_cited | 3/19 | 2/19 |
| median seconds per case | 4.6 | 13.1 |
| tokens in / out (49 cases) | 120k / 9k | 129k / 8k |

- Luna's one miss (c44) states the right facts but cites a look-alike email; EmailGrounder passes it because the email was in the evidence. Only the judge (001/11) catches this.
- `distractor_cited` is diagnostic, not an error: most hits cite the older email next to the current one to explain a change (Sol on c40: "Sommer Dental moved the time to 12:25 and kept the original appointment date.").
- Code checks are near their ceiling for both models; fact correctness and support need the judge.
- Deviation from the scope: candidates run through the Responses API, not the app's Chat Completions path (see Models, sizes, and cost in the plan).
