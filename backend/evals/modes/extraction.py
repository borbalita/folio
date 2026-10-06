"""News extraction test (plan 003): one model over the frozen newsletter dataset, scored per item.

The dataset lives only in Langfuse, so it is the source of the cases. `replay` scores a saved
local run (evals.news_runs) instead of calling the model again, for the GPT-5.5 reference.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from statistics import median

from langfuse import Evaluation, Langfuse
from openai.types.shared import ReasoningEffort
from pydantic import BaseModel

from evals.experiment import RunConfig, publication, run_experiment
from evals.langfuse_sync import Payload, remote_payloads
from evals.news_data import Newsletter
from evals.news_runs import NewsletterResult, extract_one, load_run, run_name
from evals.news_scoring import ExtractionScores, passes, pooled, score_extraction
from evals.news_sync import dataset_name
from evals.prices import PRICES_CHECKED, cost_usd
from ingest.email.news import SYSTEM_PROMPT, ExtractedItem


class ExtractionResult(BaseModel):
    key: str
    source: str
    error: str | None
    items: list[ExtractedItem] | None
    """What the model returned, kept in the local report for inspecting errors."""
    scores: ExtractionScores | None
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float | None
    seconds: float


class DatasetMissingError(RuntimeError):
    pass


def newsletter_from(payload: Payload) -> Newsletter:
    data = payload["input"]
    return Newsletter(
        key=data["key"],
        source=data["source"],
        sent_date=date.fromisoformat(data["sent_date"]),
        subject=data["subject"],
        body=data["body"],
        email_id=payload["metadata"]["email_id"],
    )


def evaluate(
    payload: Payload, extracted: NewsletterResult, model: str
) -> ExtractionResult:
    newsletter = newsletter_from(payload)
    expected = [
        ExtractedItem(blurb="", **item) for item in payload["expected_output"]["items"]
    ]
    scores = (
        score_extraction(expected, extracted.items, newsletter.body)
        if extracted.items is not None
        else None
    )
    return ExtractionResult(
        key=newsletter.key,
        source=newsletter.source,
        error=extracted.error,
        items=extracted.items,
        scores=scores,
        input_tokens=extracted.input_tokens,
        output_tokens=extracted.output_tokens,
        reasoning_tokens=extracted.reasoning_tokens,
        cost_usd=cost_usd(model, extracted.input_tokens, extracted.output_tokens),
        seconds=extracted.seconds,
    )


SCORE_NAMES = (
    "recall",
    "precision",
    "url_exact",
    "order",
    "sponsor_leaks",
    "sponsor_drops",
    "invented_urls",
)


def extraction_evaluations(result: ExtractionResult) -> list[Evaluation]:
    if result.scores is None:
        return [Evaluation(name="failed", value=1, comment=result.error)]
    s = result.scores
    comment = f"found {s.found_news} of {s.expected_news} news items, returned {s.returned_news}"
    evaluations = [
        Evaluation(name=name, value=value, comment=comment)
        for name in SCORE_NAMES
        if (value := getattr(s, name)) is not None
    ]
    if result.cost_usd is not None:
        evaluations.append(Evaluation(name="cost_usd", value=result.cost_usd))
    evaluations.append(Evaluation(name="seconds", value=result.seconds))
    return evaluations


def summarize(results: list[ExtractionResult]) -> dict[str, object]:
    scored = [r for r in results if r.scores is not None]
    totals = pooled([r.scores for r in scored])  # type: ignore[misc]
    ok, reasons = passes(totals)
    costs = [r.cost_usd for r in results]
    by_source = {
        source: pooled([r.scores for r in scored if r.source == source])  # type: ignore[misc]
        for source in sorted({r.source for r in scored})
    }
    return {
        "newsletters": len(results),
        "failed": len(results) - len(scored),
        "totals": totals,
        "by_source": by_source,
        "passes_bar": ok and len(scored) == len(results),
        "bar_failures": reasons + ([f"{len(results) - len(scored)} newsletters failed"] if len(scored) < len(results) else []),
        "cost_usd": sum(costs) if all(c is not None for c in costs) else None,
        "prices_checked": PRICES_CHECKED,
        "reasoning_tokens": sum(r.reasoning_tokens for r in results),
        "median_seconds": median(r.seconds for r in results) if results else None,
    }


def run(
    client: Langfuse,
    version: str,
    concurrency: int,
    *,
    model: str,
    effort: ReasoningEffort | None,
    replay: bool,
) -> dict[str, object]:
    name = dataset_name(version)
    payloads = remote_payloads(client, name)
    if not payloads:
        raise DatasetMissingError(f"{name} is not in Langfuse; run `python -m evals.news_sync`")
    subject = run_name(model, effort)
    saved = (
        {result.key: result for result in load_run(version, subject).results} if replay else {}
    )

    async def task(item_id: str) -> ExtractionResult:
        payload = payloads[item_id]
        key = payload["input"]["key"]
        if replay:
            extracted = saved[key]
        else:
            extracted = await asyncio.to_thread(
                extract_one, newsletter_from(payload), model, effort
            )
        result = evaluate(payload, extracted, model)
        print(f"  {key} {result.source:12} {_line(result)}")
        return result

    config = RunConfig(
        mode="extraction",
        version=version,
        subject=subject + (" (replayed)" if replay else ""),
        today=datetime.now(UTC).date(),
        prompts={"extraction_prompt": SYSTEM_PROMPT},
        concurrency=concurrency,
    )
    experiment = run_experiment(
        client,
        dataset_name=name,
        # The frozen Langfuse dataset is the only copy, so it is also the reference.
        local=payloads,
        config=config,
        run_name=f"extraction {subject}{' replay' if replay else ''} {datetime.now(UTC):%Y-%m-%d %H:%M:%S}",
        task=task,
        scores=extraction_evaluations,
    )
    ordered = sorted(experiment.results.values(), key=lambda result: result.key)
    return {
        "model": model,
        "effort": effort,
        "replayed": replay,
        "summary": summarize(ordered),
        "publication": publication(experiment),
        "results": [result.model_dump(mode="json") for result in ordered],
    }


def _line(result: ExtractionResult) -> str:
    if result.scores is None:
        return f"FAILED {result.error}"
    s = result.scores
    recall = "n/a" if s.recall is None else f"{s.recall:.2f}"
    url = "n/a" if s.url_exact is None else f"{s.url_exact:.2f}"
    return (
        f"recall {recall}  url {url}  leaks {s.sponsor_leaks}  "
        f"drops {s.sponsor_drops}  invented {s.invented_urls}"
    )


def print_summary(summary: dict[str, object]) -> None:
    totals = summary["totals"]
    assert isinstance(totals, dict)

    def fmt(value: object) -> str:
        return "n/a" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)

    print(f"\n{summary['newsletters']} newsletters, {summary['failed']} failed")
    print("  " + "  ".join(f"{key} {fmt(value)}" for key, value in totals.items()))
    cost = summary["cost_usd"]
    print(f"  cost {fmt(cost)} USD (prices checked {summary['prices_checked']}), median {fmt(summary['median_seconds'])}s")
    verdict = "PASSES" if summary["passes_bar"] else "fails"
    reasons = summary["bar_failures"]
    print(f"  {verdict} the bar" + (f": {'; '.join(reasons)}" if reasons else ""))  # type: ignore[arg-type]
