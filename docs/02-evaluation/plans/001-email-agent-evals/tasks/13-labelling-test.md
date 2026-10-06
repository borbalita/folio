# 001/13 — Labelling test

**Goal**: `run --mode labelling --variant <name>` compares Jev label variants on the labelling cases.

**Why**: Benchmarks labelling prompt changes before copying a winner into production.

**Scope**
- `labelling/variants.py`: a variant is label descriptions plus an input builder. `baseline` copies today's descriptions and reuses the production input builder; add one experimental variant (e.g. sharper newsletter/promotional wording).
- One Jev call per email per variant through the same TypeSafe provider; no retry or fallback; invalid answers counted separately.
- Metrics: accuracy, per-label precision, recall, F1 with support, macro-F1, confusion table, invalid count; reported separately for tuning and held-out.
- Runs as a Langfuse experiment on `email-labels-v1`.

**Out of scope**: changing production `labels.py`; non-Jev models.

**Likely areas affected**: `backend/evals/labelling/`, `backend/evals/scoring.py`.

**Acceptance criteria**: Baseline and the experimental variant each produce a report and Langfuse run; held-out metrics are shown separately.

**Test strategy**: Unit tests for metrics (including labels with zero support and invalid answers) and variant schema construction; manual run (negligible cost).

**Dependencies**: 001/04, 001/07.

**Review notes**: The baseline must stay in sync with production descriptions; consider a unit test asserting they match.

**Complexity**: Medium.
