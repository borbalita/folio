from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_blank_demo_user_id_is_none() -> None:
    assert Settings(demo_user_id="").demo_user_id is None  # type: ignore[arg-type]


def test_demo_user_must_differ_from_the_owner() -> None:
    same = uuid.uuid4()

    with pytest.raises(ValidationError, match="must not be the finance owner"):
        Settings(finance_owner_user_id=same, demo_user_id=same)
