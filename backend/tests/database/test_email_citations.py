from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import CheckConstraint

from app.database import chats
from app.database.chats import insert_email_citations
from app.database.models.chat.email_citation import EmailCitation

MESSAGE = uuid.UUID("00000000-0000-0000-0000-000000000020")
CHUNK = uuid.UUID("00000000-0000-0000-0000-000000000021")
NEWS = uuid.UUID("00000000-0000-0000-0000-000000000022")


def test_check_constraint_requires_exactly_one_target() -> None:
    constraint = next(
        item
        for item in EmailCitation.__table__.constraints
        if isinstance(item, CheckConstraint)
        and item.name == "ck_email_citations_one_target"
    )
    assert str(constraint.sqltext) == (
        "num_nonnulls(email_chunk_id, news_item_id, web_url) = 1"
    )


@pytest.mark.parametrize(
    "row",
    [
        {"email_chunk_id": CHUNK, "news_item_id": NEWS, "citation_index": 1},
        {"email_chunk_id": None, "news_item_id": None, "citation_index": 1},
        {
            "news_item_id": NEWS,
            "web_url": "https://example.com/a",
            "citation_index": 1,
        },
        {"web_title": "No URL", "citation_index": 1},
    ],
)
def test_insert_rejects_both_targets_and_neither(row: dict) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        insert_email_citations(MESSAGE, [row])


def test_item_and_web_citations_are_stored_with_their_own_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    monkeypatch.setattr(chats, "get_admin_client", lambda: client)

    insert_email_citations(
        MESSAGE,
        [
            {"email_chunk_id": None, "news_item_id": NEWS, "citation_index": 1},
            {
                "email_chunk_id": None,
                "news_item_id": None,
                "web_url": "https://example.com/a",
                "web_title": "A page",
                "citation_index": 2,
                "excerpt": "text",
            },
        ],
    )

    item, web = client.table.return_value.insert.call_args.args[0]
    assert item["news_item_id"] == str(NEWS)
    assert item["web_url"] is None and item["web_title"] is None
    assert web["news_item_id"] is None and web["email_chunk_id"] is None
    assert web["web_url"] == "https://example.com/a"
    assert web["web_title"] == "A page"
    assert web["excerpt"] == "text"
