"""Run one evaluation mode over a data version as a Langfuse experiment, with a local report.

Run: uv run --env-file .env.eval python -m evals.run --mode retrieval --rerank on|off
     [--version v1] [--concurrency N]
     uv run --env-file .env.eval python -m evals.run --mode answer --model gpt-6-luna
     [--version v1] [--concurrency N]
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
from evals.modes import answer, retrieval
from evals.tracing import LangfuseNotConfiguredError, eval_tracing


def _write_report(report: dict[str, object], started: datetime, name: str) -> Path:
    path = OUT_ROOT / "reports" / f"{started:%Y%m%dT%H%M%S}-{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["retrieval", "answer"], required=True)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--rerank",
        choices=["on", "off"],
        help=(
            "Retrieval mode, required: Jev evidence reranking in email search; "
            "explicit so every run says which."
        ),
    )
    parser.add_argument(
        "--model", help="Answer mode, required: the agent's OpenAI chat model."
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Cases in flight at once. Start at 1; raise to 4-5 once a mode is stable.",
    )
    args = parser.parse_args()
    if args.mode == "retrieval" and args.rerank is None:
        parser.error("--mode retrieval needs --rerank on|off")
    if args.mode == "answer" and args.model is None:
        parser.error("--mode answer needs --model")
    try:
        require_local_database(settings.database_url)
    except NotLocalDatabaseError as exc:
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
            else:
                outcome = answer.run(
                    client, args.version, args.concurrency, model=args.model
                )
                name = f"answer-{args.version}-{args.model}"
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

    mode = retrieval if args.mode == "retrieval" else answer
    mode.print_summary(outcome["summary"])
    publication = outcome["publication"]
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
