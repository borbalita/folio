from app.database import engine


def test_errors_hide_query_values(monkeypatch) -> None:
    # Values written to the database (invoice payees, amounts, message texts) must not end
    # up in error messages and logs.
    monkeypatch.setattr(engine.settings, "database_url", "postgresql://u:p@127.0.0.1:9/db")
    engine.get_engine.cache_clear()
    try:
        assert engine.get_engine().hide_parameters is True
    finally:
        engine.get_engine.cache_clear()
