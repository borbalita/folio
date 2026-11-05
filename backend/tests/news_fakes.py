"""A session stand-in for the news story queries: it applies the filters a statement carries.

It reads the compiled statement's parameters, so a query that loses its mailbox filter,
item id or (email, position) keys returns more rows here, and the test that expects fewer fails.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any

from sqlalchemy.dialects import postgresql


def news_row(
    *,
    mailbox_id: uuid.UUID,
    item_id: uuid.UUID | None = None,
    email_id: uuid.UUID | None = None,
    position: int = 0,
    title: str = "Lab ships a new model",
    body: str = "Full newsletter text.",
) -> SimpleNamespace:
    return SimpleNamespace(
        mailbox_id=mailbox_id,
        id=item_id or uuid.uuid4(),
        email_id=email_id or uuid.uuid4(),
        position=position,
        story_id=None,
        source="tldr",
        edition_date=date(2026, 11, 5),
        title=title,
        blurb="A blurb.",
        url="https://example.com/a",
        body=body,
    )


class FakeNewsDb:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.statements: list[Any] = []

    @contextmanager
    def session(self):
        yield self

    def execute(self, statement: Any) -> SimpleNamespace:
        self.statements.append(statement)
        params = statement.compile(dialect=postgresql.dialect()).params.values()
        mailboxes = [p for p in params if isinstance(p, list) and p and isinstance(p[0], uuid.UUID)]
        refs = [p for p in params if isinstance(p, list) and p and isinstance(p[0], tuple)]
        item_ids = [p for p in params if isinstance(p, uuid.UUID)]
        rows = self.rows
        if mailboxes:
            rows = [row for row in rows if row.mailbox_id in mailboxes[0]]
        if item_ids:
            rows = [row for row in rows if row.id == item_ids[0]]
        if refs:
            rows = [row for row in rows if (row.email_id, row.position) in refs[0]]
        return SimpleNamespace(all=lambda: list(rows), first=lambda: rows[0] if rows else None)
