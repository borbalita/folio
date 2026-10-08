# 001/11 — LLM judge

**Goal**: Answer and end-to-end runs also score `faithfulness` and `fact_recall` with a Claude Sonnet 5.5 judge.

**Why**: Unsupported citations and wrong facts in prose can't be checked in code.

**Scope**
- Optional `anthropic_api_key` in `app/config.py`; eval commands that need the judge fail fast without it.
- `rubrics/support.md` and `rubrics/facts.md`; structured outputs with reason before verdict.
- Support call: answer plus full text of cited chunks; per-claim `supported` / `not_supported`; simple correct inferences count as supported.
- Facts call: answer plus expected facts; per-fact `correct` / `wrong` / `missing`.
- Email text and answers passed as marked data, never instructions.
- Not-applicable when there is nothing to judge; judge errors recorded as errors, not zero scores.
- Rubric hash in run metadata.

**Out of scope**: calibration (001/12).

**Likely areas affected**: `backend/evals/judge.py`, `backend/evals/rubrics/`, `backend/app/config.py`, `backend/.env.example`.

**Acceptance criteria**: Runs show per-case `faithfulness` and `fact_recall` with per-claim and per-fact reasons visible in Langfuse.

**Test strategy**
- Unit: score arithmetic from verdict lists, not-applicable and error handling, prompt construction (data is delimited); judge with PydanticAI's test model.
- Manual: inspect verdicts on a handful of cases.

**Dependencies**: 001/09.

**Review notes**: Commit message explains the eval-only Anthropic exception (no new package; `anthropic` is already locked through `pydantic-ai`).

**Complexity**: Medium.

**Plan**: [11-judge.plan.md](11-judge.plan.md).
