from ingest.email.run import main, missing_settings


def test_missing_yahoo_settings_exit(monkeypatch) -> None:
    monkeypatch.setattr("ingest.email.run.settings.yahoo_email", None)
    monkeypatch.setattr("ingest.email.run.settings.yahoo_app_password", None)
    monkeypatch.setattr("ingest.email.run.settings.email_agent_owner_user_id", None)
    assert main([]) == 1
    assert set(missing_settings()) == {
        "YAHOO_EMAIL",
        "YAHOO_APP_PASSWORD",
        "EMAIL_AGENT_OWNER_USER_ID",
    }
