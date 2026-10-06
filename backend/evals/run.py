"""Run one evaluation mode over a data version as a Langfuse experiment, with a local report.

Run: uv run --env-file .env.eval python -m evals.run --mode retrieval [--version v1] [--concurrency N]
     uv run python -m evals.run --mode extraction --model M [--effort E] [--replay] [--version news-v1]
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
from evals.modes import extraction, retrieval
from evals.news_data import DEFAULT_NEWS_VERSION
from evals.news_runs import EFFORTS
from evals.tracing import LangfuseNotConfiguredError, eval_tracing


def _write_report(
    report: dict[str, object], started: datetime, mode: str, version: str, subject: str = ""
) -> Path:
    suffix = f"-{subject}" if subject else ""
    path = OUT_ROOT / "reports" / f"{started:%Y%m%dT%H%M%S}-{mode}-{version}{suffix}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["retrieval", "extraction"], required=True)
    parser.add_argument("--version", default=None, help="Data version (v1, or news-v1 for extraction)")
    parser.add_argument("--model", help="Extraction: the model under test")
    parser.add_argument("--effort", choices=EFFORTS, default=None, help="Extraction: reasoning effort; unset sends none")
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Extraction: score the saved local run for this model and effort instead of calling it",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Cases in flight at once. Start at 1; raise to 4-5 once a mode is stable.",
    )
    args = parser.parse_args()
    if args.mode == "extraction":
        if not args.model:
            parser.error("--mode extraction needs --model")
        return _run_extraction(args)
    args.version = args.version or DEFAULT_VERSION
    try:
        require_local_database(settings.database_url)
    except NotLocalDatabaseError as exc:
        print(exc, file=sys.stderr)
        return 1

    started = datetime.now(UTC)
    try:
        with eval_tracing() as client:
            outcome = retrieval.run(client, args.version, args.concurrency)
    except LangfuseNotConfiguredError as exc:
        print(exc, file=sys.stderr)
        return 1
    report = {
        "mode": args.mode,
        "version": args.version,
        "started_at": started.isoformat(),
        **outcome,
    }
    path = _write_report(report, started, args.mode, args.version)

    retrieval.print_summary(outcome["summary"])
    publication = outcome["publication"]
    if publication["published"]:
        print(f"langfuse: {publication['url']}")
    else:
        print(
            f"langfuse publication incomplete: {publication['errors']}", file=sys.stderr
        )
    print(f"report: {path}")
    return 0 if publication["published"] else 1


def _run_extraction(args: argparse.Namespace) -> int:
    """Extraction reads only the Langfuse dataset and calls the model; no database is used."""
    version = args.version or DEFAULT_NEWS_VERSION
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
    except (LangfuseNotConfiguredError, extraction.DatasetMissingError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    report = {"mode": "extraction", "version": version, "started_at": started.isoformat(), **outcome}
    subject = f"{args.model}@{args.effort or 'default'}{'-replay' if args.replay else ''}"
    path = _write_report(report, started, "extraction", version, subject)
    extraction.print_summary(outcome["summary"])
    publication = outcome["publication"]
    if publication["published"]:
        print(f"langfuse: {publication['url']}")
    else:
        print(f"langfuse publication incomplete: {publication['errors']}", file=sys.stderr)
    print(f"report: {path}")
    return 0 if publication["published"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
