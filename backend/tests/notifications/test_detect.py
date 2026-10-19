from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.notifications.detect import (
    InvoiceFacts,
    NewsItemFacts,
    StoryFacts,
    plan_notifications,
)

TODAY = date(2026, 10, 19)
APP = "https://folio.test"


def invoice(**overrides) -> InvoiceFacts:
    values = {
        "id": uuid.uuid4(),
        "email_id": uuid.uuid4(),
        "status": "open",
        "payee": "Stadtwerke",
        "amount": Decimal("49.90"),
        "currency": "EUR",
        "due_date": date(2026, 10, 30),
        "sender": "rechnung@stadtwerke.example",
    }
    values.update(overrides)
    return InvoiceFacts(**values)


def item(source: str, title: str = "Model X ships", url: str | None = None) -> NewsItemFacts:
    return NewsItemFacts(
        id=uuid.uuid4(), source=source, title=title, blurb="b", url=url or f"https://{source}.test/x"
    )


def news_key(it: NewsItemFacts) -> str:
    return f"news:{it.source}:{it.url}"


def plan(invoices=(), stories=(), known=frozenset(), enabled=True):
    return plan_notifications(
        list(invoices), list(stories), set(known), today=TODAY, app_url=APP, enabled=enabled
    )


def by_key(rows):
    return {row.key: row for row in rows}


def test_new_open_invoice_once() -> None:
    inv = invoice()

    first = plan(invoices=[inv])
    second = plan(invoices=[inv], known={row.key for row in first})

    [row] = first
    assert row.key == f"invoice_new:{inv.id}"
    assert row.status == "pending"
    assert row.text == (
        f"🧾 New invoice: Stadtwerke, €49.90, due 30 Oct\n{APP}/finance/invoices/{inv.email_id}"
    )
    assert second == []


def test_needs_info_says_details_missing_and_shows_no_amount() -> None:
    inv = invoice(status="needs_info", payee=None, amount=None, due_date=None)

    [row] = plan(invoices=[inv])

    assert row.text.startswith(
        "🧾 New invoice from rechnung@stadtwerke.example: details missing, check it in Folio"
    )
    assert "€" not in row.text


def test_already_paid_invoice_is_skipped() -> None:
    [row] = plan(invoices=[invoice(status="paid")])

    assert row.status == "skipped"


def test_due_in_three_days_reminds_four_does_not() -> None:
    three = invoice(due_date=date(2026, 10, 22))
    four = invoice(due_date=date(2026, 10, 23))
    known = {f"invoice_new:{three.id}", f"invoice_new:{four.id}"}

    rows = by_key(plan(invoices=[three, four], known=known))

    assert set(rows) == {f"invoice_due:{three.id}"}
    assert rows[f"invoice_due:{three.id}"].text.startswith(
        "⏰ Due in 3 days: Stadtwerke, €49.90 (22 Oct)"
    )


def test_overdue_invoice_gets_no_due_soon_reminder() -> None:
    late = invoice(due_date=date(2026, 10, 18))

    assert plan(invoices=[late], known={f"invoice_new:{late.id}"}) == []


def test_new_and_due_soon_is_one_message() -> None:
    inv = invoice(due_date=date(2026, 10, 21))

    rows = by_key(plan(invoices=[inv]))

    assert rows[f"invoice_new:{inv.id}"].status == "pending"
    assert rows[f"invoice_new:{inv.id}"].text.startswith(
        "🧾 New invoice: Stadtwerke, €49.90, due 21 Oct · due soon"
    )
    assert rows[f"invoice_due:{inv.id}"].status == "skipped"


def test_big_story_announced_once_by_its_items() -> None:
    tldr, alpha = item("tldr"), item("alpha_signal")
    story = StoryFacts(items=[tldr, alpha])

    rows = plan(stories=[story])
    pending = [row for row in rows if row.status == "pending"]

    assert {row.key for row in rows} == {news_key(tldr), news_key(alpha)}
    [message] = pending
    assert message.kind == "news_big"
    assert message.text == (
        "📰 Model X ships\nTLDR: https://tldr.test/x · Alpha Signal: https://alpha_signal.test/x"
    )


def test_rebuilt_or_grown_story_is_not_announced_again() -> None:
    tldr, alpha = item("tldr"), item("alpha_signal")
    later = item("tldr", "More on X", "https://tldr.test/more")
    known = {news_key(tldr), news_key(alpha)}

    rows = plan(stories=[StoryFacts(items=[tldr, alpha, later])], known=known)

    assert [(row.key, row.status) for row in rows] == [(news_key(later), "skipped")]


def test_reembedded_items_with_new_ids_are_not_announced_again() -> None:
    tldr, alpha = item("tldr"), item("alpha_signal")
    known = {news_key(tldr), news_key(alpha)}
    # Re-embedding deletes and recreates news items: same articles, new ids.
    again = [item("tldr", url=tldr.url), item("alpha_signal", url=alpha.url)]

    assert plan(stories=[StoryFacts(items=again)], known=known) == []


def test_disabled_settings_skip_every_new_row() -> None:
    rows = plan(invoices=[invoice()], stories=[StoryFacts(items=[item("tldr"), item("alpha_signal")])], enabled=False)

    assert rows and all(row.status == "skipped" for row in rows)
