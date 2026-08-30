"""Live hybrid-retrieval smoke against the ingested corpus.

Edit QUERIES below, then from backend/:

    uv run python -m scripts.smoke_retrieval

Hits OpenAI embeddings and Postgres. Not part of pytest.
"""

from __future__ import annotations

from app.retrieval.formatting import format_passages_for_agent
from app.retrieval.queries import SearchFilters
from app.retrieval.retriever import DocumentRetriever, RetrievedPassage

# Edit these to try other queries / filters.
QUERIES: list[tuple[str, SearchFilters | None]] = [
    ("NVIDIA data center demand", None),
    ("Apple Services revenue 2023", None),
    ("Apple Services revenue 2023", SearchFilters(ticker="AAPL")),
]


def _summarize(passage: RetrievedPassage) -> str:
    page = passage.page or "-"
    section = passage.section or "-"
    return (
        f"{passage.ticker} {passage.form} FY{passage.fiscal_year} "
        f"p.{page} {section} score={passage.fusion_score:.4f} "
        f"id={passage.chunk_id}"
    )


def main() -> None:
    retriever = DocumentRetriever()
    for query, filters in QUERIES:
        label = f"{query!r}"
        if filters is not None:
            label += f" filters={filters.model_dump(exclude_none=True)}"
        print(f"=== {label} ===")
        passages = retriever.search(query, filters=filters)
        tickers = [p.ticker for p in passages]
        print(f"count={len(passages)} tickers={tickers}")
        for i, passage in enumerate(passages, start=1):
            print(f"  {i}. {_summarize(passage)}")
        print(format_passages_for_agent(passages)[:800])
        print()


if __name__ == "__main__":
    main()
