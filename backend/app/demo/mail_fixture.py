"""The demo user's everyday mail: a committed fixture with fixed labels and embeddings.

`mail_fixture.draft.json` holds the text (written by hand, invented people on .example domains)
and the appointment rules; `mail_fixture.json` adds one embedding and token count per email,
made once by `python -m app.demo.embed_mail_fixture`. Vectors use the news fixture's encoding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.config import settings
from app.demo.mail_dates import AppointmentRule
from app.demo.news_fixture import decode_vector

DRAFT_PATH = Path(__file__).with_name("mail_fixture.draft.json")
FIXTURE_PATH = Path(__file__).with_name("mail_fixture.json")
# The script renders the appointment placeholders for this day before embedding; seeding renders
# them for the reset day, and the few changed digits don't matter to semantic search.
REFERENCE_DAY = date(2026, 10, 15)


@dataclass(frozen=True, slots=True)
class FixtureMail:
    key: str
    from_name: str
    from_address: str
    subject: str
    body: str
    label: str
    days_ago: int
    embedding: list[float] | None = None
    token_count: int | None = None


def _rules(data: dict[str, Any]) -> dict[str, AppointmentRule]:
    return {
        name: AppointmentRule(**rule) for name, rule in data["appointments"].items()
    }


def _mail(raw: dict[str, Any], *, with_vectors: bool) -> FixtureMail:
    fields = {
        k: raw[k]
        for k in (
            "key",
            "from_name",
            "from_address",
            "subject",
            "body",
            "label",
            "days_ago",
        )
    }
    if with_vectors:
        return FixtureMail(
            **fields,
            embedding=decode_vector(raw["embedding"]),
            token_count=raw["token_count"],
        )
    return FixtureMail(**fields)


def load_draft(
    path: Path = DRAFT_PATH,
) -> tuple[dict[str, AppointmentRule], list[FixtureMail]]:
    data = json.loads(path.read_text())
    return _rules(data), [_mail(raw, with_vectors=False) for raw in data["emails"]]


def load_fixture(
    path: Path = FIXTURE_PATH,
) -> tuple[dict[str, AppointmentRule], list[FixtureMail]]:
    data = json.loads(path.read_text())
    if data["embedding_model"] != settings.openai_embedding_model:
        raise ValueError(
            f"Demo mail fixture embedding model {data['embedding_model']!r} differs from "
            f"settings ({settings.openai_embedding_model!r}); rerun app.demo.embed_mail_fixture."
        )
    if data["embedding_dimensions"] != settings.openai_embedding_dimensions:
        raise ValueError(
            "Demo mail fixture embedding dimensions differ from settings; "
            "rerun app.demo.embed_mail_fixture."
        )
    return _rules(data), [_mail(raw, with_vectors=True) for raw in data["emails"]]
