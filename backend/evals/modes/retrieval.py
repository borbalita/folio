"""Retrieval test: the real email search with each case's fixed probe; no chat model involved."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.config import settings
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailRetriever
from evals.cases import RagCase
from evals.dataset import IdMap
from evals.scoring import RetrievalScores, emails_in_rank_order, retrieval_scores


class RetrievalResult(BaseModel):
    case_id: str
    kind: str
    split: str
    answerable: bool
    expected_email_keys: list[str]
    retrieved_email_keys: list[str]
    distractors_retrieved: list[str]
    scores: RetrievalScores


def chunk_owners(id_map: IdMap) -> dict[UUID, str]:
    return {
        chunk_id: key
        for key, ids in id_map.emails.items()
        for chunk_id in ids.chunk_ids
    }


def run_case(case: RagCase, owners: dict[UUID, str]) -> RetrievalResult:
    filters = EmailSearchFilters(
        user_id=case.user_id,
        mailbox_ids=[case.mailbox_id],
        **case.probe_filters.model_dump(),
    )
    passages = EmailRetriever().search(case.probe_query, filters=filters)
    ranked = emails_in_rank_order((p.chunk_id for p in passages), owners)
    return RetrievalResult(
        case_id=case.case_id,
        kind=case.kind,
        split=case.split,
        answerable=case.answerable,
        expected_email_keys=case.expected_email_keys,
        retrieved_email_keys=ranked,
        distractors_retrieved=[key for key in ranked if key in case.distractor_keys],
        scores=retrieval_scores(
            ranked, case.expected_email_keys, k=settings.retrieval_top_k
        ),
    )
