"""Run one mode as a Langfuse experiment over a synced dataset, keeping every result locally.

Scores are computed inside the task, so the local report never depends on Langfuse; evaluators
only forward them. If publishing fails, the results are kept and nothing is re-run.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from langfuse import Evaluation, Langfuse, propagate_attributes
from pydantic import BaseModel

from app.config import BACKEND_ROOT
from evals.langfuse_sync import Payload, plan_sync, remote_payloads

EVAL_TAG = "eval"


@dataclass(frozen=True)
class RunConfig:
    mode: str
    version: str
    subject: str
    """The model or labelling variant under test."""
    today: date
    prompts: dict[str, str]
    """Prompt or rubric name -> text; only hashes go into the run metadata."""
    concurrency: int = 1


@dataclass
class ExperimentRun[R: BaseModel]:
    results: dict[str, R]
    """Dataset item ID -> result, for every item whose task finished."""
    missing: list[str]
    published: bool
    run_name: str
    url: str | None = None
    errors: list[str] = field(default_factory=list)


class DatasetOutOfSyncError(RuntimeError):
    pass


def git_commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=BACKEND_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()

    commit = git("rev-parse", "--short", "HEAD")
    return f"{commit}-dirty" if git("status", "--porcelain") else commit


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def run_metadata(config: RunConfig, commit: str) -> dict[str, str]:
    return {
        "git_commit": commit,
        "mode": config.mode,
        "subject": config.subject,
        "data_version": config.version,
        "today": config.today.isoformat(),
        **{
            f"{name}_hash": text_hash(text)
            for name, text in sorted(config.prompts.items())
        },
    }


def run_experiment[R: BaseModel](
    client: Langfuse,
    *,
    dataset_name: str,
    local: dict[str, Payload],
    config: RunConfig,
    run_name: str,
    task: Callable[[str], Awaitable[R]],
    scores: Callable[[R], list[Evaluation]],
) -> ExperimentRun[R]:
    """Run `task` on every dataset item (by item ID) and publish `scores` per item."""
    remote = remote_payloads(client, dataset_name)
    plan = plan_sync(local, remote or {})
    if remote is None or plan.create or plan.conflicts:
        raise DatasetOutOfSyncError(
            f"{dataset_name} does not match the committed cases; run `python -m evals.langfuse_sync`"
        )

    results: dict[str, R] = {}
    tags = [EVAL_TAG, f"mode:{config.mode}", f"data:{config.version}"]

    async def experiment_task(*, item: Any, **_: Any) -> R:
        with propagate_attributes(tags=tags):
            result = await task(item.id)
        results[item.id] = result
        return result

    def evaluator(*, output: R, **_: Any) -> list[Evaluation]:
        return scores(output)

    dataset = client.get_dataset(dataset_name)
    errors: list[str] = []
    url = None
    try:
        outcome = dataset.run_experiment(
            name=f"email-{config.mode}",
            run_name=run_name,
            description=f"{config.mode} on {dataset_name} with {config.subject}",
            task=experiment_task,
            evaluators=[evaluator],
            max_concurrency=config.concurrency,
            metadata=run_metadata(config, git_commit()),
        )
        url = outcome.dataset_run_url
        if outcome.dataset_run_id is None:
            errors.append("Langfuse returned no dataset run")
    except Exception as exc:  # noqa: BLE001 - keep local results whatever the upload did
        errors.append(f"{type(exc).__name__}: {exc}")
    missing = sorted(set(local) - set(results))
    if missing:
        errors.append(f"{len(missing)} items failed; see the Langfuse traces")
    return ExperimentRun(
        results=results,
        missing=missing,
        published=not errors,
        run_name=run_name,
        url=url,
        errors=errors,
    )


def publication(run: ExperimentRun) -> dict[str, object]:
    return {
        "published": run.published,
        "run_name": run.run_name,
        "url": run.url,
        "missing_items": run.missing,
        "errors": run.errors,
    }
