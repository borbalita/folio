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


def item(
    source: str,
    title: str = "Model X ships",
    url: str | None = None,
    *,
    email_id: uuid.UUID | None = None,
    position: int = 0,
    alert: str | None = None,
) -> NewsItemFacts:
    return NewsItemFacts(
        id=uuid.uuid4(),
        email_id=email_id or uuid.uuid4(),
        position=position,
        source=source,
        title=title,
        blurb="b",
        url=f"https://{source}.test/x" if url is None else url,
        alert_status=alert,
    )


def news_key(it: NewsItemFacts) -> str:
    return f"news:{it.email_id}:{it.position}"


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
        "📰 Model X ships\nb\nTLDR: https://tldr.test/x · Alpha Signal: https://alpha_signal.test/x"
    )


def test_rebuilt_or_grown_story_is_not_announced_again() -> None:
    tldr, alpha = item("tldr"), item("alpha_signal")
    later = item("tldr", "More on X", "https://tldr.test/more", position=1)
    known = {news_key(tldr), news_key(alpha)}

    rows = plan(stories=[StoryFacts(items=[tldr, alpha, later])], known=known)

    assert [(row.key, row.status) for row in rows] == [(news_key(later), "skipped")]


def test_reembedded_items_with_new_ids_are_not_announced_again() -> None:
    tldr, alpha = item("tldr"), item("alpha_signal")
    known = {news_key(tldr), news_key(alpha)}
    # Re-embedding deletes and recreates news items: same email and position, new ids.
    again = [
        item("tldr", email_id=tldr.email_id, position=tldr.position),
        item("alpha_signal", email_id=alpha.email_id, position=alpha.position),
    ]

    assert plan(stories=[StoryFacts(items=again)], known=known) == []


def test_disabled_settings_skip_every_new_row() -> None:
    rows = plan(invoices=[invoice()], stories=[StoryFacts(items=[item("tldr"), item("alpha_signal")])], enabled=False)

    assert rows and all(row.status == "skipped" for row in rows)



def test_items_without_links_are_still_told_apart_and_not_linked() -> None:
    # Alpha Signal items mostly carry no link.
    first = StoryFacts(items=[item("tldr"), item("alpha_signal", url="")])
    second = StoryFacts(items=[item("tldr", "Other news"), item("alpha_signal", "Other news", url="")])

    rows = plan(stories=[first])
    rows += plan(stories=[second], known={row.key for row in rows})

    pending = [row for row in rows if row.status == "pending"]
    assert len(pending) == 2
    assert pending[0].text == "📰 Model X ships\nb\nTLDR: https://tldr.test/x"


def security_story(alert: str, title: str = "PHP2Shell exploited", *, big: bool = False) -> StoryFacts:
    return StoryFacts(items=[item("tldr", title, alert=alert)], big=big)


def test_new_update_and_repeat_on_separate_stories() -> None:
    new, update = security_story("new", "Flaw A"), security_story("update", "Flaw B")
    # A repeat is not loaded as an alert story at all; a security-marked non-big story with only
    # a repeat item reaches the planner as a story without an alert.
    repeat = StoryFacts(items=[item("tldr", "Flaw C", alert="repeat")], big=False)

    rows = plan(stories=[new, update, repeat])

    pending = {row.key: row for row in rows if row.status == "pending"}
    assert set(pending) == {news_key(new.items[0]), news_key(update.items[0])}
    assert pending[news_key(new.items[0])].kind == "news_security"
    assert pending[news_key(new.items[0])].text.startswith("🔒 Flaw A\n")
    assert pending[news_key(update.items[0])].text.startswith("🔒 Update: Flaw B\n")
    assert pending[news_key(update.items[0])].update is True
    assert news_key(repeat.items[0]) not in {row.key for row in rows}


def test_a_big_security_story_sends_one_security_message() -> None:
    tldr, alpha = item("tldr", alert="new"), item("alpha_signal")
    story = StoryFacts(items=[tldr, alpha], big=True)

    rows = plan(stories=[story])

    assert {row.key for row in rows} == {news_key(tldr), news_key(alpha)}
    [message] = [row for row in rows if row.status == "pending"]
    assert message.kind == "news_security"
    assert message.text.startswith("🔒 ")
    assert "📰" not in message.text


def test_a_big_story_with_only_a_repeat_is_still_announced_as_big() -> None:
    story = StoryFacts(items=[item("tldr", alert="repeat"), item("alpha_signal")], big=True)

    [message] = [row for row in plan(stories=[story]) if row.status == "pending"]

    assert message.kind == "news_big"


def test_a_story_that_gains_a_security_item_after_its_message_went_out_sends_nothing() -> None:
    first = item("tldr", position=1)
    announced = {news_key(first)}
    later = item("alpha_signal", alert="update", position=4)
    story = StoryFacts(items=[first, later], big=True)

    rows = plan(stories=[story], known=announced)

    assert [row for row in rows if row.status == "pending"] == []
    assert [row.key for row in rows] == [news_key(later)]


def test_a_new_item_wins_over_an_update_item_in_one_story() -> None:
    story = StoryFacts(items=[item("tldr", alert="update"), item("alpha_signal", alert="new")])

    [message] = [row for row in plan(stories=[story]) if row.status == "pending"]

    assert message.update is False and message.text.startswith("🔒 Model X")


def test_security_rows_are_skipped_while_telegram_is_off() -> None:
    rows = plan(stories=[security_story("new")], enabled=False)

    assert [row.status for row in rows] == ["skipped"]
    assert rows[0].kind == "news_security"


def test_the_security_fallback_message_has_the_lock_and_the_links() -> None:
    from app.notifications.detect import security_fallback_text

    story = security_story("update")

    assert security_fallback_text(story.items, update=True) == (
        "🔒 Update: PHP2Shell exploited\nb\nTLDR: https://tldr.test/x"
    )


def test_news_security_is_an_allowed_kind_in_the_model_and_the_migration() -> None:
    import re
    from pathlib import Path

    from app.database.models.notification import NotificationKind

    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    sources = [p.read_text() for p in versions.glob("*security*.py")]
    assert len(sources) == 1
    assert "ck_notifications_kind" in sources[0]
    allowed = set(re.findall(r"'(\w+)'", re.search(r'"kind IN \(([^)]*)\)"', sources[0]).group(1)))
    assert allowed == {kind.value for kind in NotificationKind}
    assert "news_security" in allowed
