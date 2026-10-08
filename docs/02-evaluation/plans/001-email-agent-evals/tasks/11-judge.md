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

## Verified

2026-10-08, on data v2 (49 cases), GPT-6 Luna through the Responses API, judge `claude-sonnet-5-5`:

- Runs show per-case `faithfulness` and `fact_recall` with per-claim and per-fact reasons in Langfuse: passed. [Answer run](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/84171765-2c66-49f1-87b1-5451e3c44ca0), [end-to-end run](https://cloud.langfuse.com/project/cmtk97zmg0038ad0frh0pv72c/datasets/cmuwing8j079ead0cc8ushb4c/runs/a80054ed-6c2d-48c6-845e-e56e7dfd7ddc). Checked in the browser on c38: the Scores tab lists each claim and fact with verdict and reason, and the metadata has `rubric_support_hash` and `rubric_facts_hash`. No judge errors in either run.
- Unit tests: score arithmetic, not-applicable cases, errors as `judge_error`, prompt delimiting and escaping, reason before verdict (`tests/evals/test_judge.py`, judge on `FunctionModel`).
- Verdicts read by hand on the flagged cases. A first run without the date gave two false flags: "the deadline has passed" (c13, c18) marked unsupported because the judge didn't know today. The judge now gets `<today>`; on the rerun it accepts the past tense on c18 by comparing against today. Remaining flags look right:
  - c44 (first run): Luna cites a look-alike email and states another event's post and date; faithfulness 0. The code checks pass this case, so this is the gap the judge was for.
  - c07, c14: "valid through 5 August" where the email says "use before 5 August".
  - c38: an original date stated without citing the email that has it.
- Answer run with the judge: faithfulness 0.986, fact_recall 1.000; judge cost about $0.008 per case.
- PR: [borbalita/folio#10](https://github.com/borbalita/folio/pull/10).

Trusted only after calibration (001/12).
