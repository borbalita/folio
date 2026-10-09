# 001/14 — First benchmark

**Goal**: Run the full benchmark once and write up the results.

**Why**: This is the portfolio-visible outcome and the first real check of the whole workflow.

**Scope**
- Answer and end-to-end runs for Luna and Sol, three repeats each, with the judge.
- Labelling runs for baseline and the experimental variant.
- Compare per case (A-passes/B-fails counts), note cases that flip between repeats, check actual cost against the estimate.
- Error analysis: read failing cases and group them into failure types; note follow-ups in the plan's Later list.
- Results summary in `backend/evals/README.md`.

**Out of scope**: acting on findings (prompt or model changes).

**Likely areas affected**: `backend/evals/README.md`.

**Acceptance criteria**: The README contains a results section with per-dimension scores per model, per-case comparison, labelling held-out metrics, cost, and main failure types.

**Test strategy**: Not applicable; review the write-up.

**Dependencies**: 001/10, 001/12, 001/13.

**Review notes**: Requires explicit go-ahead for the paid run (about $12). Report differences only as large as the sample supports.

**Complexity**: Small.
