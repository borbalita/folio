"""Run one evaluation mode over a data version as a Langfuse experiment, with a local report.

Run: uv run --env-file .env.eval python -m evals.run --mode retrieval [--version v1] [--concurrency N]
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
from evals.modes import retrieval
from evals.tracing import LangfuseNotConfiguredError, eval_tracing


def _write_report(
    report: dict[str, object], started: datetime, mode: str, version: str
) -> Path:
    path = OUT_ROOT / "reports" / f"{started:%Y%m%dT%H%M%S}-{mode}-{version}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["retrieval"], required=True)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Cases in flight at once. Start at 1; raise to 4-5 once a mode is stable.",
    )
    args = parser.parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
