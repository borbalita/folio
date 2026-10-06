# 001/05 — Ingest data into Docker

**Goal**: `prepare` loads `data/v1/` into the eval database through normal ingestion and verifies the result.

**Why**: The RAG modes search this mailbox; the stored-label check exercises production labelling including retry and fallback.

**Scope**
- Second half of `prepare`: parse the `.eml` files and call `ingest_messages` for user A's active mailbox with real embeddings and Jev labelling.
- Compare stored labels with the scenario; print mismatches and a summary.
- Write a gitignored map from scenario email keys to database email and chunk IDs.

**Out of scope**: scoring; Langfuse.

**Likely areas affected**: `backend/evals/prepare.py`.

**Acceptance criteria**
- After `prepare`, every scenario email exists in the database with chunks and embeddings.
- The label report lists mismatches by email key.
- The ID map covers every email.

**Test strategy**
- Unit: label comparison and ID-map building with fake rows.
- Manual: one real `prepare` run (cents).

**Dependencies**: 001/01, 001/04.

**Review notes**: Label mismatches are reported, never overwritten with scenario labels.

**Complexity**: Small.
