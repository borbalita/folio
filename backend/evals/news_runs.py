"""Run one extraction model over the exported newsletters and keep every output (plan 003/03).

These runs happen before the dataset is reviewed and synced, so they are local only. The
outputs feed the review file; the GPT-5.5 reference outputs are also scored later instead of
being bought twice. Results go to the gitignored evals/out/news-runs/<version>/.

Run: uv run python -m evals.news_runs --model gpt-5.4-nano --effort none [--concurrency 4]
     uv run python -m evals.news_runs --from-report evals/out/reports/<report>.json --version news-v2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import APIError
from openai.types.shared import ReasoningEffort
from pydantic import BaseModel

from evals.dataset import OUT_ROOT
from evals.news_data import DEFAULT_NEWS_VERSION, Newsletter, load_newsletters
from evals.prices import cost_usd
from ingest.email.news import ExtractedItem, request_extraction
from ingest.email.parse import ParsedMessage

EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


class NewsletterResult(BaseModel):
    key: str
    items: list[ExtractedItem] | None
    """None when the call failed or the model returned nothing parseable."""
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    seconds: float = 0.0


class RunFile(BaseModel):
    version: str
    model: str
    effort: str | None
    """The effort actually sent; None means the API default."""
    started_at: datetime
    results: list[NewsletterResult]


def run_name(model: str, effort: str | None) -> str:
    return f"{model}@{effort or 'default'}"


def runs_dir(version: str) -> Path:
    return OUT_ROOT / "news-runs" / version


def load_run(version: str, name: str) -> RunFile:
    return RunFile.model_validate_json((runs_dir(version) / f"{name}.json").read_text())


def _as_parsed(newsletter: Newsletter) -> ParsedMessage:
    # Extraction only reads subject and body; the rest is filler for the shared type.
    return ParsedMessage(
        message_id=newsletter.key,
        provider_message_id=newsletter.key,
        folder="INBOX",
        subject=newsletter.subject,
        from_address="",
        to_addresses=[],
        sent_at=datetime.combine(newsletter.sent_date, datetime.min.time(), UTC),
        body=newsletter.body,
        attachment_filenames=(),
        attachments=(),
    )


def extract_one(
    newsletter: Newsletter, model: str, effort: ReasoningEffort | None
) -> NewsletterResult:
    started = time.monotonic()
    try:
        completion = request_extraction(
            _as_parsed(newsletter), model=model, reasoning_effort=effort
        )
    except APIError as exc:
        return NewsletterResult(
            key=newsletter.key,
            items=None,
            error=f"{type(exc).__name__}: {exc}",
            seconds=time.monotonic() - started,
        )
    seconds = time.monotonic() - started
    usage = completion.usage
    details = usage.completion_tokens_details if usage else None
    parsed = completion.choices[0].message.parsed
    return NewsletterResult(
        key=newsletter.key,
        items=parsed.items if parsed else None,
        error=None if parsed else "no parsed output",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        reasoning_tokens=(details.reasoning_tokens or 0) if details else 0,
        seconds=seconds,
    )


def summarize(run: RunFile) -> str:
    done = [result for result in run.results if result.items is not None]
    input_tokens = sum(result.input_tokens for result in run.results)
    output_tokens = sum(result.output_tokens for result in run.results)
    reasoning = sum(result.reasoning_tokens for result in run.results)
    cost = cost_usd(run.model, input_tokens, output_tokens)
    items = sum(len(result.items or []) for result in done)
    sponsors = sum(sum(item.sponsor for item in result.items or []) for result in done)
    seconds = sorted(result.seconds for result in run.results)
    median = seconds[len(seconds) // 2] if seconds else 0.0
    cost_text = f"${cost:.2f}" if cost is not None else "unknown price"
    return (
        f"{run_name(run.model, run.effort)}: {len(done)}/{len(run.results)} ok, "
        f"{items} items ({sponsors} flagged sponsor), "
        f"tokens in {input_tokens} / out {output_tokens} (reasoning {reasoning}), "
        f"{cost_text}, median {median:.1f}s per newsletter"
    )


def run_from_report(report: dict[str, Any], version: str) -> RunFile:
    """A saved run rebuilt from an official extraction report, without calling the model.

    Reports keep each newsletter's items, so a paid run can become an answer key or be
    replayed against another dataset version holding the same newsletters.
    """
    missing = [r["key"] for r in report["results"] if "items" not in r]
    if missing:
        raise ValueError(
            f"report has no items for {missing[:5]}; it predates item logging"
        )
    return RunFile(
        version=version,
        model=report["model"],
        effort=report["effort"],
        started_at=datetime.fromisoformat(report["started_at"]),
        results=[
            NewsletterResult(
                key=r["key"],
                items=r["items"],
                error=r["error"],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                reasoning_tokens=r["reasoning_tokens"],
                seconds=r["seconds"],
            )
            for r in report["results"]
        ],
    )


def _save(run: RunFile) -> Path:
    path = runs_dir(run.version) / f"{run_name(run.model, run.effort)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--effort", choices=EFFORTS, default=None)
    parser.add_argument("--version", default=DEFAULT_NEWS_VERSION)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--from-report",
        type=Path,
        help="Save an official extraction report's items as a run for --version instead of calling a model",
    )
    args = parser.parse_args()
    if args.from_report:
        run = run_from_report(json.loads(args.from_report.read_text()), args.version)
        print(summarize(run))
        print(f"saved {_save(run)}")
        return 0
    if not args.model:
        parser.error("--model is required unless --from-report is given")

    newsletters = load_newsletters(args.version)
    if not newsletters:
        print(
            f"no exported newsletters for {args.version}; run evals.news_export",
            file=sys.stderr,
        )
        return 1

    started = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(
            pool.map(
                lambda item: extract_one(item, args.model, args.effort), newsletters
            )
        )
    run = RunFile(
        version=args.version,
        model=args.model,
        effort=args.effort,
        started_at=started,
        results=results,
    )
    path = _save(run)
    print(summarize(run))
    for result in results:
        if result.error:
            print(f"  {result.key}: {result.error}")
    print(f"saved {path}")
    return 0 if all(result.items is not None for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
