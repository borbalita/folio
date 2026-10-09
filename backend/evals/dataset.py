"""Where a data version's files live, and the local map from scenario keys to database IDs."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from evals.cases import LabelCase, RagCase
from evals.scenario import Scenario

EVALS_ROOT = Path(__file__).resolve().parent
DATA_ROOT = EVALS_ROOT / "data"
OUT_ROOT = EVALS_ROOT / "out"
DEFAULT_VERSION = "v1"


class StoredEmailIds(BaseModel):
    email_id: UUID
    chunk_ids: list[UUID]


class IdMap(BaseModel):
    """Scenario email key -> database IDs, written by prepare for one data version."""

    version: str
    emails: dict[str, StoredEmailIds]


def data_dir(version: str) -> Path:
    return DATA_ROOT / version


def load_scenario(version: str) -> Scenario:
    return Scenario.model_validate_json(
        (data_dir(version) / "scenario.json").read_text()
    )


def load_rag_cases(version: str) -> list[RagCase]:
    lines = (data_dir(version) / "rag_cases.jsonl").read_text().splitlines()
    return [RagCase.model_validate_json(line) for line in lines if line]


def load_label_cases(version: str) -> list[LabelCase]:
    lines = (data_dir(version) / "label_cases.jsonl").read_text().splitlines()
    return [LabelCase.model_validate_json(line) for line in lines if line]


def id_map_path(version: str) -> Path:
    return OUT_ROOT / f"ids-{version}.json"


def load_id_map(version: str) -> IdMap:
    path = id_map_path(version)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run `python -m evals.prepare` first")
    return IdMap.model_validate_json(path.read_text())
