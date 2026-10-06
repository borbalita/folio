"""Preset evidence for the answer test: search is replaced, so only answering is measured."""

from __future__ import annotations

import random
from uuid import UUID

from sqlalchemy.orm import Session

from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailPassage, EmailRetriever, load_passages
from evals.cases import RagCase
from evals.dataset import IdMap


def evidence_email_keys(case: RagCase) -> list[str]:
    """Expected and distractor emails, in an order fixed per case.

    Shuffled so the answer isn't always first; seeded by case ID so every run and model
    sees the same order. Unanswerable cases without distractors get nothing.
    """
    keys = list(dict.fromkeys(case.expected_email_keys + case.distractor_keys))
    random.Random(case.case_id).shuffle(keys)
    return keys


def evidence_chunk_ids(case: RagCase, id_map: IdMap) -> list[UUID]:
    return [
        chunk_id
        for key in evidence_email_keys(case)
        for chunk_id in id_map.emails[key].chunk_ids
    ]


def load_evidence(session: Session, case: RagCase, id_map: IdMap) -> list[EmailPassage]:
    chunk_ids = evidence_chunk_ids(case, id_map)
    if not chunk_ids:
        return []
    filters = EmailSearchFilters(user_id=case.user_id, mailbox_ids=[case.mailbox_id])
    loaded = load_passages(session, chunk_ids, filters)
    return [loaded[chunk_id] for chunk_id in chunk_ids]


class ReplayRetriever(EmailRetriever):
    """Returns the same preset passages for every search, whatever the query or filters."""

    def __init__(self, passages: list[EmailPassage]) -> None:
        super().__init__(rerank=False)
        self.passages = passages
        self.queries_seen: list[str] = []

    def search(
        self,
        query: str,
        *,
        filters: EmailSearchFilters,
        session: Session | None = None,
        question: str | None = None,
    ) -> list[EmailPassage]:
        self.queries_seen.append(query)
        return list(self.passages)
