from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import ClassVar, Self

import pytest

from app.config import settings
from app.finance import notify

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


class FakeSMTP:
    sent: ClassVar[list[EmailMessage]] = []
    logins: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        assert (host, port) == ("smtp.mail.yahoo.com", 465)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        FakeSMTP.logins.append((user, password))

    def send_message(self, message: EmailMessage) -> None:
        FakeSMTP.sent.append(message)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.sent = []
    FakeSMTP.logins = []
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(settings, "yahoo_email", "owner@yahoo.test")
    monkeypatch.setattr(settings, "yahoo_app_password", "app-pw")
    monkeypatch.setattr(
        settings, "enable_banking_redirect_url", "https://folio.test/finance/accounts/callback"
    )
    return FakeSMTP


def test_email_body_links_to_accounts_page(smtp: type[FakeSMTP]) -> None:
    sent = notify.send_expiry_notice("ING", "14d", NOW + timedelta(days=13), NOW)

    (message,) = smtp.sent
    assert sent
    assert message["Subject"] == "Folio: ING bank access expires in 13 days"
    assert message["From"] == message["To"] == "owner@yahoo.test"
    assert "https://folio.test/finance/accounts" in message.get_content()
    assert "/callback" not in message.get_content()
    assert smtp.logins == [("owner@yahoo.test", "app-pw")]


def test_expired_subject(smtp: type[FakeSMTP]) -> None:
    notify.send_expiry_notice("N26", "expired", NOW - timedelta(days=1), NOW)

    assert smtp.sent[0]["Subject"] == "Folio: N26 bank access has expired"


def test_missing_yahoo_settings_skip_the_email(
    smtp: type[FakeSMTP], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "yahoo_app_password", None)

    assert not notify.send_expiry_notice("ING", "3d", NOW + timedelta(days=2), NOW)
    assert smtp.sent == []
