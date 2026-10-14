import pytest

from ingest.bank.run import main, missing_settings


def test_cli_reports_missing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingest.bank.run.settings.finance_owner_user_id", None)
    monkeypatch.setattr("ingest.bank.run.settings.enable_banking_app_id", None)
    monkeypatch.setattr("ingest.bank.run.settings.enable_banking_private_key", "k")
    monkeypatch.setattr("ingest.bank.run.settings.enable_banking_redirect_url", "u")

    assert main() == 1
    assert missing_settings() == ["FINANCE_OWNER_USER_ID", "ENABLE_BANKING_APP_ID"]
