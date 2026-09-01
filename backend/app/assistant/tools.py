"""Retrieval tool implementations used by the document agent."""

from __future__ import annotations

from uuid import UUID

from app.assistant.deps import DocumentAgentDeps
from app.retrieval.formatting import format_passages_for_agent
from app.retrieval.queries import SearchFilters
from app.retrieval.retriever import RetrievedPassage


def register_passages(
    deps: DocumentAgentDeps, passages: list[RetrievedPassage]
) -> None:
    for passage in passages:
        deps.seen_ids.add(passage.chunk_id)
        deps.seen_passages[passage.chunk_id] = passage
        for neighbor in passage.neighbors:
            deps.seen_ids.add(neighbor.chunk_id)
            deps.seen_passages[neighbor.chunk_id] = neighbor


def execute_search_filings(
    deps: DocumentAgentDeps,
    query: str,
    *,
    ticker: str | None = None,
    fiscal_years: list[int] | None = None,
    form: str | None = None,
) -> str:
    filters = SearchFilters(ticker=ticker, fiscal_years=fiscal_years, form=form)
    passages = deps.retriever.search(query, filters=filters)
    register_passages(deps, passages)
    return format_passages_for_agent(passages)


def execute_read_chunk(deps: DocumentAgentDeps, chunk_id: UUID) -> str:
    passage = deps.retriever.passage_by_id(chunk_id)
    if passage is None:
        return "No matching passages found in the filing corpus."
    register_passages(deps, [passage])
    return format_passages_for_agent([passage])


def execute_read_surrounding_chunks(deps: DocumentAgentDeps, chunk_id: UUID) -> str:
    passages = deps.retriever.surrounding_passages(chunk_id)
    register_passages(deps, passages)
    return format_passages_for_agent(passages)
