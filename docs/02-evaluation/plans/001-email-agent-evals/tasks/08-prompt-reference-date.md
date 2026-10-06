# 001/08 — Optional reference date in the email prompt

**Goal**: `email_prompt` accepts an optional `today`, defaulting to the current date in the configured timezone.

**Why**: Relative-date questions ("last week") need a fixed date in evaluations. This is the plan's only production change, so it gets its own review.

**Scope**: Add `today: date | None = None` to `email_prompt`; no change to callers or behaviour when omitted.

**Out of scope**: `run_email_agent` changes; eval code.

**Likely areas affected**: `backend/app/email_assistant/agent.py`, its tests.

**Acceptance criteria**
- Without `today`, the prompt is unchanged.
- With `today`, the prompt states that date.

**Test strategy**: Unit tests for both cases; `uv run pytest -m "not integration"`.

**Dependencies**: none.

**Review notes**: Keep the change minimal.

**Complexity**: Small.
