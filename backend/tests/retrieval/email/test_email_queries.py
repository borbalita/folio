from __future__ import annotations

from uuid import UUID

from app.retrieval.email.queries import EmailQueries, EmailSearchFilters

USER = UUID("00000000-0000-0000-0000-000000000001")
OWNED = UUID("00000000-0000-0000-0000-000000000010")
QUERIES = EmailQueries()


def _filters(**overrides: object) -> EmailSearchFilters:
    values: dict[str, object] = {"user_id": USER, "mailbox_ids": [OWNED]}
    values.update(overrides)
    return EmailSearchFilters.model_validate(values)


def test_sql_is_scoped_to_the_user_and_active_mailboxes() -> None:
    filters = _filters()
    for sql in (QUERIES.semantic_sql(filters), QUERIES.full_text_sql(filters)):
        assert "m.user_id = :user_id" in sql
        assert "m.id = ANY(:mailbox_ids)" in sql
        assert "m.is_active IS TRUE" in sql


def test_filters_narrow_sender_label_dates_and_mailbox() -> None:
    filters = _filters(
        since="2026-09-01",
        until="2026-09-28",
        label="invoice",
        sender="rent",
        mailbox="yahoo",
    )
    sql = QUERIES.semantic_sql(filters)
    assert "(e.sent_at AT TIME ZONE :email_timezone)::date >= :since" in sql
    assert "(e.sent_at AT TIME ZONE :email_timezone)::date <= :until" in sql
    assert "e.label = :label" in sql
    assert "e.from_address ILIKE :sender" in sql
    assert "lower(m.display_name) = lower(:mailbox)" in sql
    assert "lower(m.address) = lower(:mailbox)" in sql


def test_sender_param_matches_anywhere_in_the_address() -> None:
    clause = QUERIES.filter_clause(_filters(sender="rent"))
    assert clause.params["sender"] == "%rent%"
