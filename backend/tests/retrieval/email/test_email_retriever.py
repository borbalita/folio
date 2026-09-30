from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailPassage, EmailRetriever
from app.retrieval.queries import RankedHit

USER = UUID("00000000-0000-0000-0000-000000000001")
OWNED = UUID("00000000-0000-0000-0000-000000000010")
CHUNK = UUID("00000000-0000-0000-0000-0000000000aa")
EMAIL = UUID("00000000-0000-0000-0000-0000000000bb")


def _filters(**overrides: object) -> EmailSearchFilters:
    values: dict[str, object] = {"user_id": USER, "mailbox_ids": [OWNED]}
    values.update(overrides)
    return EmailSearchFilters.model_validate(values)


def _patch_hits(monkeypatch: pytest.MonkeyPatch, loaded: dict) -> None:
    monkeypatch.setattr("app.retrieval.base.embed_query", lambda _query: [0.1])
    monkeypatch.setattr(
        "app.retrieval.base.extract_fts_keywords",
        lambda query, *, system_prompt: query,
    )
    monkeypatch.setattr(
        "app.retrieval.email.queries.EmailQueries.semantic",
        lambda *_args, **_kwargs: [RankedHit(chunk_id=CHUNK, rank=1, score=0.9)],
    )
    monkeypatch.setattr(
        "app.retrieval.email.queries.EmailQueries.full_text",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.retrieval.email.retriever.load_passages",
        lambda _session, _ids, _filters: loaded,
    )


def test_search_returns_from_subject_and_date(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = datetime(2026, 9, 4, 8, 0, tzinfo=UTC)
    passage = EmailPassage(
        chunk_id=CHUNK,
        email_id=EMAIL,
        text="Rent is due Friday.",
        from_address="landlord@example.com",
        subject="September rent",
        sent_at=sent,
        mailbox_name="Yahoo",
        fusion_score=0.0,
    )
    _patch_hits(monkeypatch, {CHUNK: passage})

    found = EmailRetriever().search("rent", filters=_filters(), session=object())

    assert len(found) == 1
    assert found[0].from_address == "landlord@example.com"
    assert found[0].subject == "September rent"
    assert found[0].sent_at == sent
    assert found[0].fusion_score > 0


def test_search_drops_a_chunk_outside_the_user_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_hits(monkeypatch, {})

    assert EmailRetriever().search("rent", filters=_filters(), session=object()) == []


def test_search_passes_mail_keywords_to_full_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_hits(monkeypatch, {})
    prompts: list[str] = []

    def extract(_query: str, *, system_prompt: str) -> str:
        prompts.append(system_prompt)
        return "Telekom invoice"

    monkeypatch.setattr("app.retrieval.base.extract_fts_keywords", extract)
    fts = MagicMock(return_value=[])
    monkeypatch.setattr("app.retrieval.email.queries.EmailQueries.full_text", fts)

    EmailRetriever().search(
        "What did Telekom charge me last month?", filters=_filters(), session=object()
    )

    assert fts.call_args.args[1] == "Telekom invoice"
    assert prompts == [EmailRetriever.keyword_prompt]


def test_search_with_no_mailbox_does_not_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_query: str) -> list[float]:
        raise AssertionError("embed should not run")

    monkeypatch.setattr("app.retrieval.base.embed_query", fail)

    found = EmailRetriever().search(
        "rent", filters=_filters(mailbox_ids=[]), session=object()
    )

    assert found == []
