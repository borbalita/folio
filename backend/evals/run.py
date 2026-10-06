"""Run one evaluation mode over a data version and write a local report.

Run: uv run --env-file .env.eval python -m evals.run --mode retrieval [--version v1]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime

from app.config import settings
from evals.dataset import DEFAULT_VERSION, OUT_ROOT, load_id_map, load_rag_cases
from evals.guard import NotLocalDatabaseError, require_local_database
from evals.modes.retrieval import RetrievalResult, chunk_owners, run_case
from evals.scoring import mean

METRICS = ("recall", "precision", "mrr")


def summarize(results: list[RetrievalResult]) -> dict[str, object]:
    """Averages overall and per case kind; unanswerable cases are only counted."""

    def averages(group: list[RetrievalResult]) -> dict[str, float | None]:
        return {m: mean(getattr(r.scores, m) for r in group) for m in METRICS}

    by_kind: dict[str, list[RetrievalResult]] = defaultdict(list)
    for result in results:
        by_kind[result.kind].append(result)
    answerable = [r for r in results if r.answerable]
    return {
        "cases": len(results),
        "unanswerable_cases": len(results) - len(answerable),
        "overall": averages(answerable),
        "by_kind": {kind: averages(group) for kind, group in sorted(by_kind.items())},
        "distractor_retrieved_cases": sum(
            1 for r in results if r.distractors_retrieved
        ),
    }


def run_retrieval(version: str) -> dict[str, object]:
    owners = chunk_owners(load_id_map(version))
    results = []
    for case in load_rag_cases(version):
        result = run_case(case, owners)
        results.append(result)
        print(f"  {case.case_id} {case.kind:14} {_scores_line(result)}")
    return {
        "summary": summarize(results),
        "results": [result.model_dump(mode="json") for result in results],
    }


def _scores_line(result: RetrievalResult) -> str:
    if not result.answerable:
        return f"n/a (unanswerable, {len(result.retrieved_email_keys)} emails returned)"
    s = result.scores
    return f"recall {s.recall:.2f}  precision {s.precision:.2f}  mrr {s.mrr:.2f}"


def _format(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["retrieval"], required=True)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args()
    try:
        require_local_database(settings.database_url)
    except NotLocalDatabaseError as exc:
        print(exc, file=sys.stderr)
        return 1

    started = datetime.now(UTC)
    report = {
        "mode": args.mode,
        "version": args.version,
        "started_at": started.isoformat(),
        "top_k": settings.retrieval_top_k,
        **run_retrieval(args.version),
    }
    path = (
        OUT_ROOT
        / "reports"
        / f"{started:%Y%m%dT%H%M%S}-{args.mode}-{args.version}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"\n{summary['cases']} cases, {summary['unanswerable_cases']} unanswerable (recall n/a)"
    )
    for name, averages in [
        ("overall", summary["overall"]),
        *summary["by_kind"].items(),
    ]:
        print(
            f"  {name:15} " + "  ".join(f"{m} {_format(averages[m])}" for m in METRICS)
        )
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
