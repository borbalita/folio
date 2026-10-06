# 001/02 — Scoping integration test

**Goal**: Prove against a real database that email search never returns another user's mail or mail from an inactive mailbox.

**Why**: Existing tests only check the scope SQL text and mocked filtering. Scoping is a security property and belongs in the normal test suite.

**Scope**
- An `@pytest.mark.integration` test in `tests/retrieval/email/` that uses the 001/01 seeded database.
- Ingest a few handwritten `ParsedMessage`s into user A's active and inactive mailboxes and user B's mailbox via `ingest_messages`, with injected `embed` and `classifier` so no network calls are made.
- Run `EmailRetriever().search` as user A with a query matching all messages; assert only user A's active-mailbox mail is returned.
- Update the `integration` marker description to include the local eval database.

**Out of scope**: news retrieval scoping; agent-level tests.

**Likely areas affected**: `tests/retrieval/email/`, `backend/pyproject.toml` (marker text).

**Acceptance criteria**
- `uv run --env-file .env.eval pytest -m integration tests/retrieval/email` passes.
- Temporarily removing the `is_active` or `user_id` condition from `scope_clause` makes the test fail.
- The test refuses to run against a non-localhost database.

**Test strategy**: The test itself; manually verify the failure case once.

**Dependencies**: 001/01.

**Review notes**: Search's keyword helper calls OpenAI; inject or stub it so the test is network-free, without weakening what is asserted about the SQL scope.

**Complexity**: Small.
