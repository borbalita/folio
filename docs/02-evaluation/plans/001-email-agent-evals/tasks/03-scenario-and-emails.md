# 001/03 — Scenario and emails

**Goal**: `generate` writes a structured scenario and about 60 realistic `.eml` files that faithfully contain the scenario's facts.

**Why**: Expected answers are only correct by construction if the emails contain exactly the planned facts.

**Scope**
- Pydantic scenario schema: senders, emails with intended label, key facts (amounts, dates, subjects), planted traps (near-duplicates, date boundaries, borderline labels), and planned unanswerable topics.
- LLM scenario generation with its own short label definitions (not the production descriptions); about 12 emails per model-assigned label; no AI newsletters.
- LLM rendering of each email to `.eml` (headers, plain or HTML body), parsed back with the production `parse_rfc822`.
- Fact check in code: each rendered email contains its key facts; failures are re-rendered with a bounded number of attempts.
- Output to a working directory, not yet `data/v1/`.

**Out of scope**: cases and questions (001/04); ingestion.

**Likely areas affected**: `backend/evals/generate.py`, `backend/evals/scenario.py`.

**Acceptance criteria**
- One command produces the scenario JSON and about 60 `.eml` files.
- Every email parses with `parse_rfc822` and passes the fact check.
- Label counts are roughly balanced, and the scenario includes each trap type.

**Test strategy**
- Unit: fact check accepts and rejects hand-written examples; scenario schema validation.
- Manual: read a sample of emails for realism.

**Dependencies**: none.

**Review notes**: Generation model and prompts must not reuse production label descriptions (circularity). Bound retries so a bad prompt can't loop on paid calls.

**Complexity**: Medium.
