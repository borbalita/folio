from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from evals import news_export
from evals.news_data import load_newsletters


def _email(sent_at: datetime, subject: str, source: str = "tldr") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        message_id=f"{sent_at.isoformat()}@example.com",
        sent_at=sent_at,
        subject=subject,
        body="Item one\nItem two",
        newsletter_source=source,
    )


def test_newsletters_are_keyed_in_send_order_with_local_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(news_export.settings, "email_timezone", "Europe/Berlin")
    late = _email(datetime(2026, 9, 2, 6, 0, tzinfo=UTC), "Later", "alpha_signal")
    # 23:30 UTC is already the next day in Berlin.
    early = _email(datetime(2026, 9, 1, 23, 30, tzinfo=UTC), "Earlier")

    newsletters = news_export.to_newsletters([late, early])

    assert [(item.key, item.subject) for item in newsletters] == [
        ("n01", "Earlier"),
        ("n02", "Later"),
    ]
    assert newsletters[0].sent_date == date(2026, 9, 2)
    assert newsletters[1].source == "alpha_signal"
    assert newsletters[0].email_id == str(early.id)


def test_encoded_subjects_are_decoded() -> None:
    assert news_export.decode_subject("=?UTF-8?Q?Gro=C3=9Fe_News?=") == "Große News"
    assert news_export.decode_subject("Plain subject") == "Plain subject"
    assert news_export.decode_subject("=?x-bogus?Q?abc?=") == "=?x-bogus?Q?abc?="


def test_export_writes_files_and_refuses_to_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "news-test" / "newsletters"
    monkeypatch.setattr(news_export, "news_dir", lambda version: out)
    monkeypatch.setattr("evals.news_data.news_dir", lambda version: out)
    newsletters = news_export.to_newsletters(
        [_email(datetime(2026, 9, 1, 8, 0, tzinfo=UTC), "One")]
    )
    monkeypatch.setattr(news_export, "_read_newsletters", lambda: newsletters)
    monkeypatch.setattr("sys.argv", ["news_export", "--version", "news-test"])

    assert news_export.main() == 0
    assert [item.key for item in load_newsletters("news-test")] == ["n01"]

    assert news_export.main() == 1
    assert "already has files" in capsys.readouterr().err


def test_export_fails_when_no_newsletters_are_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(news_export, "news_dir", lambda version: tmp_path / "empty")
    monkeypatch.setattr(news_export, "_read_newsletters", list)
    monkeypatch.setattr("sys.argv", ["news_export"])

    assert news_export.main() == 1
    assert not (tmp_path / "empty").exists()
