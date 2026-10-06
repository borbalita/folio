# 001/15 — Documentation

**Goal**: Someone can run the evaluations and understand the method from `backend/evals/README.md`.

**Why**: Usage knowledge and the evaluation method should outlive this plan.

**Scope**
- Commands are added to `backend/evals/README.md` by each task as it lands (Docker and `.env.eval` in 001/01, `generate` in 001/03, and so on). This task checks them end to end.
- Short "How this evaluation works": steps measured separately, code checks versus judge, calibration, fair comparison and noise, held-out cases, scenario-first data.
- Link from `docs/02-evaluation/` and `docs/README.md`; mark the plan's deviations, if any.

**Out of scope**: results (001/14 writes them).

**Likely areas affected**: `backend/evals/README.md`, `docs/README.md`.

**Acceptance criteria**: Following only the README, a fresh checkout reaches a retrieval run.

**Test strategy**: Manual walk-through from a clean database.

**Dependencies**: 001/14.

**Review notes**: Describe what was built, not the plan.

**Complexity**: Small.
