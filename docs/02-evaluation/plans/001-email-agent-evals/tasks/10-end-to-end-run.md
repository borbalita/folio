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

**Plan**: [10-end-to-end-run.plan.md](10-end-to-end-run.plan.md).

## Verified

2026-10-07, on data v2 (49 cases, 13 unanswerable), both models through the Responses API at default effort, reranking off and on:

- Luna and Sol runs in Langfuse with per-case scores, tool arguments, and retrieval recall: passed. Rerank off: [Luna](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/75627aa6-1c7b-4095-8063-b8b47ad32071), [Sol](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/34ebdb11-1e22-43ad-8d0e-185de783d07f). Rerank on: [Luna](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/58d77314-76f0-497c-9e47-73c6ce9e4db8), [Sol](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/12a614e1-8868-489f-b6ba-5a96465b6594). Checked in the browser: the experiment view shows `search_recall` next to the answer scores per item, and the c01 trace output has `searches` (query, filters, emails returned) and `steps` (tool arguments).
- Recall across several tool calls: passed (unit tests in `tests/evals/test_e2e.py`, including an agent run with two searches through `RecordingRetriever`).
- PR: [borbalita/folio#7](https://github.com/borbalita/folio/pull/7).

| | Luna, rerank off | Luna, rerank on | Sol, rerank off | Sol, rerank on |
| --- | --- | --- | --- | --- |
| refusal_correct | 36/49 | 35/49 | 49/49 | 49/49 |
| evidence_cited | 23/36 | 23/36 | 36/36 | 36/36 |
| search_recall | 23/36 | 23/36 | 36/36 | 36/36 |
| grounding_pass | 49/49 | 44/44 | 49/49 | 45/46 |
| distractor_cited | 1/13 | 1/13 | 2/13 | 1/12 |
| searches (49 cases) | 66 | 57 | 67 | 73 |
| median seconds per case | 7.9 | 8.4 | 9.9 | 10.6 |
| tokens in / out (49 cases) | 200k / 9k | 100k / 8k | 238k / 8k | 122k / 8k |

- All 13 of Luna's misses are one failure: it passes the sender's display name as `sender` ("Lindenstrom Billing"), but the filter matches `from_address` only (`billing@lindenstrom.example`), so the search returns nothing and Luna correctly refuses on empty evidence. 18 of Luna's 21 sender filters were names; 7 of Sol's 8 were addresses. The instructions already say "sender matches the From address". Fixing it (matching the display name too, or a sharper tool description) is a product change outside this task.
- In the answer test Luna scored 35/36 on evidence; here search filters, not answering, decide the gap.
- Reranking halves input tokens (dropped passages never reach the model) and adds under a second per case. It can't help Luna's misses, which return nothing to rerank. `grounding_pass` applies to fewer cases with reranking on because some searches return nothing.
- Luna, rerank on, c47 (unanswerable): answered from e94, the one email reranking kept. Sol, rerank on, c17: cited the same chunk twice under index [1] (`duplicate_index`), a model error unrelated to reranking.
- One run each, so single-case differences are within noise; 001/14 repeats runs three times.
