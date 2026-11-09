from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.config import Settings, settings


def test_the_suite_ignores_local_langfuse_keys() -> None:
    assert not settings.langfuse_public_key
    assert not settings.langfuse_secret_key


def test_blank_demo_user_id_is_none() -> None:
    assert Settings(demo_user_id="").demo_user_id is None  # type: ignore[arg-type]


def test_demo_user_must_differ_from_the_owner() -> None:
    same = uuid.uuid4()

    with pytest.raises(ValidationError, match="must not be the finance owner"):
        Settings(finance_owner_user_id=same, demo_user_id=same)


def test_demo_user_must_differ_from_the_email_agent_owner() -> None:
    same = uuid.uuid4()

    with pytest.raises(ValidationError, match="must not be the email agent owner"):
        Settings(email_agent_owner_user_id=same, demo_user_id=same)
