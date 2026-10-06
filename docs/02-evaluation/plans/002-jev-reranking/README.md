# 002 — Harder retrieval data and Jev evidence reranking

- Created: 2026-10-06
- Status: In progress
- Current stage: 002/01 done; decide how 002/03 measures reranking before 002/02.

## Approval state

Approved on 2026-10-06: harder retrieval cases in a new data version v2, a Jev reranking step in production email search that reorders and drops, no third-party reranking library, and doing this before 001/09 so the answer and end-to-end tests run on v2.

## Problem

Plan 001's retrieval test on v1 scores recall 1.0 and MRR 0.976: questions name the sender and month, every answer sits in one email, and the mailbox is small. That benchmark can't show whether a retrieval change helps. A reranking step is wanted as a portfolio feature, and it needs data where retrieval can actually fail.

## Decisions

### v2 extends v1; v1 stays frozen

v1 was synced to Langfuse and is frozen. v2 starts from a copy of v1 (all 65 emails and 31 cases, same IDs and wording) and adds emails and cases, so v1 results remain a baseline and v2 numbers include v1's cases. Rejected: regenerating from scratch (loses the baseline and the reviewed emails).

### Harder cases are planned in the scenario

One generation step plans story lines of linked emails, filler mail on overlapping topics, and *planned questions* that reference scenario facts by email key and fact name:

- `multi_email`: the answer's facts are spread over two to four emails.
- `superseded`: a later email changes a value (moved meeting, corrected amount); the question asks for the current value and the older email is a distractor.
- `vague`: no sender name or exact month; the person refers to roles and relative time ("my landlord", "last month").
- `unanswerable`: a near-miss question, e.g. a month or sender the mailbox doesn't have, with look-alike emails as distractors.

Expected emails and facts still come from scenario data in code; only question wording uses an LLM. Questions ask for stated facts, never arithmetic. New emails may not repeat a fact value of a v1 email, so v1 cases stay unambiguous.

### Reranking: Jev judges evidence, then reorder and drop

`EmailRetriever` fuses about 20 candidates (`email_rerank_candidates`) instead of 10. Jev scores each passage in parallel for whether it contains evidence for the question: `full`, `partial`, or `none`. Passages are ordered full, then partial, each in fused order; `none` is dropped; the result is capped at `retrieval_top_k`. If nothing survives, the tool returns "No matching mail", which should help refusals. A failed Jev call keeps the passage at its fused position (fail open), so an outage degrades to today's search.

Jev sees the search query and, when the agent is running, the user's question, since the agent's tool queries are often keyword-like. `email_rerank` (default on) turns the step off; evals pass it explicitly to compare both.

Written in the repo, reusing the TypeSafe provider from labelling: it is about 40 lines, the relevance prompt is the part to tune and evaluate, and a community wrapper over an SDK we already use fails the dependency policy. A local cross-encoder comparison is optional later and would stay in dev dependencies.

## Tasks

- [x] 002/01 — v2 data: story lines, filler, planned questions; `prepare` and `sync` for v2; retrieval baseline on v2.
- [ ] 002/02 — Jev evidence reranker in `EmailRetriever` with settings, fail-open, tracing, and unit tests.
- [ ] 002/03 — Retrieval test with reranking off vs on (quality and latency per search); later the answer and end-to-end tests from plan 001 compare both.

## v2 baseline (2026-10-06)

v2 has 115 emails and 49 cases (v1's 31 plus 5 multi_email, 5 superseded, 5 vague, 3 unanswerable), synced as `email-rag-v2` and `email-labels-v2`. Retrieval without reranking, concurrency 4:

| kind | recall@10 | recall@1 | recall@3 | MRR |
| --- | --- | --- | --- | --- |
| overall (36 answerable) | 1.000 | | | 0.972 |
| multi_email | 1.000 | 0.43 | 0.93 | 1.000 |
| superseded | 1.000 | 0.80 | 1.00 | 0.900 |
| vague | 1.000 | 0.90 | 1.00 | 1.000 |
| near_duplicate | 1.000 | 0.75 | 1.00 | 0.875 |

Recall@10 is still saturated. What the new cases do show: every superseded and multi_email search returns its planned distractors (outdated values, look-alikes) at ranks 2–6, and every unanswerable search returns 10 emails, with a look-alike in the top 3 for 12 of 13. Reorder-and-drop targets exactly that, so it shows up in precision, distractors returned, and empty results on unanswerable cases rather than in recall, which mainly guards against wrong drops.

## Risks

- **Still too easy**: check the v2 baseline before building the reranker; add harder cases if recall stays near 1.0.
- **Wrong drops**: a `none` on a real evidence email hides it; visible as lower recall with reranking on.
- **Latency**: about 20 Jev calls per search; measured in 002/03.
