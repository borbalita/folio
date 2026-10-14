"""Bank sync CLI, run by Railway cron. Run from backend/: uv run python -m ingest.bank"""

from __future__ import annotations

import sys

from app.config import settings
from app.finance.transaction_sync import run_bank_sync
from app.logging import configure_logging


def missing_settings() -> list[str]:
    return [
        name
        for name, value in (
            ("FINANCE_OWNER_USER_ID", settings.finance_owner_user_id),
            ("ENABLE_BANKING_APP_ID", settings.enable_banking_app_id),
            ("ENABLE_BANKING_PRIVATE_KEY", settings.enable_banking_private_key),
            ("ENABLE_BANKING_REDIRECT_URL", settings.enable_banking_redirect_url),
        )
        if not value
    ]


def main() -> int:
    configure_logging()
    missing = missing_settings()
    if missing:
        print(
            "Bank sync needs " + ", ".join(missing) + ". Set them in backend/.env.",
            file=sys.stderr,
        )
        return 1
    assert settings.finance_owner_user_id is not None
    counts = run_bank_sync(settings.finance_owner_user_id)
    print(", ".join(f"{name}: {value}" for name, value in counts.items()))
    return 0
