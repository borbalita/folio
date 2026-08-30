"""Bounded, grep-style text for PydanticAI tool responses."""

from __future__ import annotations

from app.retrieval.retriever import RetrievedPassage

MAX_PASSAGE_EXCERPT_CHARS = 800
MAX_AGENT_OUTPUT_CHARS = 12_000


def _format_one_passage(passage: RetrievedPassage, *, include_neighbors: bool) -> str:
    page = f" p.{passage.page}" if passage.page else ""
    section = f" ({passage.section})" if passage.section else ""
    excerpt = passage.text.strip()
    if len(excerpt) > MAX_PASSAGE_EXCERPT_CHARS:
        excerpt = excerpt[:MAX_PASSAGE_EXCERPT_CHARS] + "..."
    header = (
        f"{passage.ticker} {passage.form} FY{passage.fiscal_year}{page}{section} "
        f"[{passage.chunk_id}]: {excerpt}"
    )
    lines = [header]
    if include_neighbors:
        for neighbor in passage.neighbors:
            neighbor_excerpt = neighbor.text.strip()
            if len(neighbor_excerpt) > MAX_PASSAGE_EXCERPT_CHARS:
                neighbor_excerpt = neighbor_excerpt[:MAX_PASSAGE_EXCERPT_CHARS] + "..."
            lines.append(
                f"  neighbor idx={neighbor.chunk_index} [{neighbor.chunk_id}]: "
                f"{neighbor_excerpt}"
            )
    return "\n".join(lines)


def format_passages_for_agent(passages: list[RetrievedPassage]) -> str:
    if not passages:
        return "No matching passages found in the filing corpus."

    blocks = [_format_one_passage(p, include_neighbors=True) for p in passages]
    output = "\n\n".join(blocks)
    if len(output) > MAX_AGENT_OUTPUT_CHARS:
        output = output[: MAX_AGENT_OUTPUT_CHARS - 3] + "..."
    return output
