"""Run one evaluation mode over a data version as a Langfuse experiment, with a local report.

Run: uv run --env-file .env.eval python -m evals.run --mode retrieval --rerank on|off
     [--version v1] [--concurrency N]
     uv run --env-file .env.eval python -m evals.run --mode answer --model gpt-6-luna
     [--effort none] [--version v1] [--concurrency N]
     uv run --env-file .env.eval python -m evals.run --mode e2e --model gpt-6-luna
     --rerank on|off [--effort none] [--version v1] [--concurrency N]
     uv run python -m evals.run --mode extraction --model gpt-5.6-luna [--effort none]
     [--replay] [--version news-v2] [--concurrency N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from evals.dataset import DEFAULT_VERSION, OUT_ROOT
from evals.guard import NotLocalDatabaseError, require_local_database
from evals.judge import JudgeNotConfiguredError, judge_model
from evals.modes import answer, e2e, extraction, retrieval
from evals.news_data import SCORING_NEWS_VERSION
from evals.news_runs import EFFORTS
from evals.tracing import LangfuseNotConfiguredError, eval_tracing


def _write_report(report: dict[str, object], started: datetime, name: str) -> Path:
    path = OUT_ROOT / "reports" / f"{started:%Y%m%dT%H%M%S}-{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["retrieval", "answer", "e2e", "extraction"], required=True
    )
    parser.add_argument(
        "--version",
        default=None,
        help=f"Data version (default {DEFAULT_VERSION}; {SCORING_NEWS_VERSION} for extraction)",
    )
    parser.add_argument(
        "--rerank",
        choices=["on", "off"],
        help=(
            "Retrieval and e2e modes, required: Jev evidence reranking in email search; "
            "explicit so every run says which."
        ),
    )
    parser.add_argument(
        "--model",
        help=(
            "Answer and e2e modes, required: the agent's OpenAI chat model. "
            "Extraction mode, required: the extraction model under test."
        ),
    )
    parser.add_argument(
        "--effort",
        choices=EFFORTS,
        default=None,
        help=(
            "Answer, e2e, and extraction modes: reasoning effort; unset sends none, so the "
            "model's default applies."
        ),
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help=(
            "Answer and e2e modes: skip the Claude judge (faithfulness, fact_recall), "
            "which needs ANTHROPIC_API_KEY."
        ),
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help=(
            "Extraction mode: score the saved local run for this model and effort "
            "instead of calling it."
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Cases in flight at once. Start at 1; raise to 4-5 once a mode is stable.",
    )
    args = parser.parse_args()
    if args.mode in ("retrieval", "e2e") and args.rerank is None:
        parser.error(f"--mode {args.mode} needs --rerank on|off")
    if args.mode in ("answer", "e2e", "extraction") and args.model is None:
        parser.error(f"--mode {args.mode} needs --model")
    if args.mode == "extraction":
        return _run_extraction(args)
    args.version = args.version or DEFAULT_VERSION
    try:
        require_local_database(settings.database_url)
    except NotLocalDatabaseError as exc:
        print(exc, file=sys.stderr)
        return 1

    judge = None
    if args.mode in ("answer", "e2e") and not args.no_judge:
        try:
            judge = judge_model()
        except JudgeNotConfiguredError as exc:
            print(exc, file=sys.stderr)
            return 1

    started = datetime.now(UTC)
    try:
        with eval_tracing() as client:
            if args.mode == "retrieval":
                outcome = retrieval.run(
                    client, args.version, args.concurrency, rerank=args.rerank == "on"
                )
                name = f"retrieval-{args.version}-rerank-{args.rerank}"
            elif args.mode == "e2e":
                outcome = e2e.run(
                    client,
                    args.version,
                    args.concurrency,
                    model=args.model,
                    effort=args.effort,
                    rerank=args.rerank == "on",
                    judge=judge,
                )
                name = (
                    f"e2e-{args.version}-{args.model}-effort-{args.effort or 'default'}"
                    f"-rerank-{args.rerank}"
                )
            else:
                outcome = answer.run(
                    client,
                    args.version,
                    args.concurrency,
                    model=args.model,
                    effort=args.effort,
                    judge=judge,
                )
                name = f"answer-{args.version}-{args.model}-effort-{args.effort or 'default'}"
    except LangfuseNotConfiguredError as exc:
        print(exc, file=sys.stderr)
        return 1
    report = {
        "mode": args.mode,
        "version": args.version,
        "started_at": started.isoformat(),
        **outcome,
    }
    path = _write_report(report, started, name)

    mode = {"retrieval": retrieval, "answer": answer, "e2e": e2e}[args.mode]
    mode.print_summary(outcome["summary"])
    return _print_publication(outcome, path)


def _run_extraction(args: argparse.Namespace) -> int:
    """Extraction reads only the Langfuse dataset and calls the model; no database is used."""
    version = args.version or SCORING_NEWS_VERSION
    started = datetime.now(UTC)
    try:
        with eval_tracing() as client:
            outcome = extraction.run(
                client,
                version,
                args.concurrency,
                model=args.model,
                effort=args.effort,
                replay=args.replay,
            )
    except (
        LangfuseNotConfiguredError,
        extraction.DatasetMissingError,
        FileNotFoundError,
    ) as exc:
        print(exc, file=sys.stderr)
        return 1
    report = {
        "mode": "extraction",
        "version": version,
        "started_at": started.isoformat(),
        **outcome,
    }
    subject = f"{args.model}@{args.effort or 'default'}"
    replay = "-replay" if args.replay else ""
    path = _write_report(report, started, f"extraction-{version}-{subject}{replay}")
    extraction.print_summary(outcome["summary"])
    return _print_publication(outcome, path)


def _print_publication(outcome: dict[str, object], path: Path) -> int:
    publication = outcome["publication"]
    assert isinstance(publication, dict)
    if publication["published"]:
        print(f"langfuse: {publication['url']}")
    else:
        print(
            f"langfuse publication incomplete: {publication['errors']}", file=sys.stderr
        )
    print(f"report: {path}")
    return 0 if publication["published"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
