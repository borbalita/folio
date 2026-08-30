"""Live agent smoke: retrieval tools + LLM + grounding.

Edit QUESTIONS below, then from backend/:

    uv run python -m scripts.smoke_agent

Hits OpenAI (chat + embeddings) and Postgres. Does not persist chat messages.
Not part of pytest.
"""

from __future__ import annotations

import asyncio
import uuid

from app.assistant.agent import run_agent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.grounding import GroundingError, validate_grounded_answer
from app.retrieval.retriever import DocumentRetriever

# Client-brief example questions, plus one the corpus cannot answer.
QUESTIONS: list[str] = [
    "Across Apple's 2021–2025 10-Ks, how did the revenue mix between iPhone, Services, Mac, iPad, and Wearables change, and which category appears to have contributed most to any mix shift?",
    "For Amazon, compare AWS operating income and margin against North America and International from 2021–2025. In which years did AWS appear to fund losses or weaker profitability elsewhere?",
    "How did NVIDIA describe demand drivers, customer concentration, and supply constraints for its Data Center business from fiscal 2021 through fiscal 2025?",
    "Across Microsoft's 2021–2025 filings, what changed in the way the company describes Azure, AI infrastructure, and cloud capacity constraints?",
    "For Alphabet, how did Google Search, YouTube ads, Google Network, subscriptions/platforms/devices, and Google Cloud revenue trends differ across the available 10-Ks?",
    "Which of the five companies added, removed, or materially changed risk-factor language related to AI, cloud infrastructure, export controls, supply chain concentration, or regulation between 2021 and 2025?",
    "For Apple and NVIDIA, what do the filings say about supplier concentration or dependence on third-party manufacturing, and did the wording become more or less urgent over time?",
    "Compare capital expenditures and purchase commitments for Microsoft, Alphabet, Amazon, and NVIDIA. What do the filings imply about the scale and timing of AI/cloud infrastructure investment?",
    "For each company, summarize the most important geographic revenue exposures disclosed in the latest 10-K, then identify any year-over-year changes that could matter to an analyst.",
    "If an analyst asks whether the filings prove that generative AI improved margins for any of these companies, what evidence exists in the corpus, and where should the bot refuse to infer beyond the filings?",
    "What was Tesla's fiscal 2023 automotive gross margin?",
]


async def _run_one(question: str) -> dict[str, object]:
    deps = DocumentAgentDeps(
        user_id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        retriever=DocumentRetriever(),
    )
    print(f"=== {question} ===", flush=True)
    turn = await run_agent(question, deps)
    try:
        validate_grounded_answer(turn.answer, deps.seen_ids)
        grounding = "ok"
    except GroundingError as exc:
        grounding = f"failed: {exc}"

    answer = turn.answer
    print(f"grounding={grounding}", flush=True)
    print(f"insufficient_evidence={answer.insufficient_evidence}")
    print(f"usage={turn.usage}")
    print(f"seen_ids={len(deps.seen_ids)}")
    print(answer.answer)
    for citation in answer.citations:
        passage = deps.seen_passages.get(citation.chunk_id)
        source = ""
        if passage is not None:
            source = (
                f" {passage.ticker} {passage.form} FY{passage.fiscal_year}"
                f" p.{passage.page or '-'}"
            )
        print(
            f"  [{citation.citation_index}] {citation.chunk_id}{source}"
            f" excerpt={citation.excerpt!r}",
        )
    print()
    return {
        "grounding": grounding,
        "insufficient": answer.insufficient_evidence,
        "citations": len(answer.citations),
        "seen": len(deps.seen_ids),
    }


async def main() -> None:
    rows: list[dict[str, object]] = []
    for question in QUESTIONS:
        rows.append(await _run_one(question))
    print("=== SUMMARY ===")
    for i, row in enumerate(rows, start=1):
        print(
            f"Q{i} grounding={row['grounding']} "
            f"insufficient={row['insufficient']} "
            f"citations={row['citations']} seen={row['seen']}",
        )


if __name__ == "__main__":
    asyncio.run(main())
