# 001/04 — Cases and data v1

**Goal**: Derive RAG and labelling cases from the scenario and commit the first data version.

**Why**: Every test mode reads these case files; committing them freezes a comparable benchmark.

**Scope**
- `rag_cases.jsonl` (~30 cases, ~8 unanswerable): case ID, question, fixed `today`, user, retrieval probe (query and filters), expected email keys, expected facts, answerable flag, optional distractor keys, tuning/held-out split.
- `label_cases.jsonl`: email key, expected label, split (~60/40, balanced by label).
- Expected results are derived in code from the scenario; only question wording uses an LLM, instructed not to copy email phrasing.
- Pydantic models for both case files, used by every mode.
- Write scenario, emails, and cases to `backend/evals/data/v1/` and commit.

**Out of scope**: running any mode.

**Likely areas affected**: `backend/evals/generate.py`, `backend/evals/cases.py`, `backend/evals/data/v1/`.

**Acceptance criteria**
- Both files validate against their models.
- Every expected email key exists in the scenario; unanswerable cases have no expected emails.
- Splits are balanced by label (labelling) and by trap type (RAG).

**Test strategy**: Unit tests for derivation (given a small hand-written scenario, the expected cases come out) and split balance.

**Dependencies**: 001/03.

**Review notes**: Check that no expected answer comes from an LLM reading the email; only from scenario data.

**Complexity**: Medium.
