from __future__ import annotations

import uuid

import pytest
from sqlalchemy import CheckConstraint

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
        "(email_chunk_id IS NOT NULL) <> (news_item_id IS NOT NULL)"
    )


@pytest.mark.parametrize(
    "row",
    [
        {"email_chunk_id": CHUNK, "news_item_id": NEWS, "citation_index": 1},
        {"email_chunk_id": None, "news_item_id": None, "citation_index": 1},
    ],
)
def test_insert_rejects_both_targets_and_neither(row: dict) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        insert_email_citations(MESSAGE, [row])
