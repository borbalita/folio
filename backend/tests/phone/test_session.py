from __future__ import annotations

import uuid

from app.config import settings
from app.phone.personas import PERSONAS, persona_by_id
from app.phone.session import CallLimiter, session_config

USER = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def test_friend_is_the_only_persona_you_can_call_for_now() -> None:
    available = [persona.id for persona in PERSONAS if persona.available]

    assert available == ["friend"]
    assert {persona.id for persona in PERSONAS} == {"friend", "doctor", "interviewer"}


def test_friend_session_has_its_prompt_voice_and_transcription() -> None:
    friend = persona_by_id("friend")
    assert friend is not None

    config = session_config(friend)

    assert config["type"] == "realtime"
    assert config["model"] == settings.openai_realtime_model
    assert config["instructions"] == friend.instructions()
    assert "friend" in config["instructions"].lower()
    assert config["audio"]["output"]["voice"] == friend.voice
    assert (
        config["audio"]["input"]["transcription"]["model"]
        == settings.openai_realtime_transcribe_model
    )


def test_unknown_persona_is_none() -> None:
    assert persona_by_id("pirate") is None


def test_limiter_refuses_once_the_hour_is_full_and_frees_up_after() -> None:
    now = [1000.0]
    limiter = CallLimiter(per_hour=2, clock=lambda: now[0])

    assert limiter.allow(USER)
    assert limiter.allow(USER)
    assert not limiter.allow(USER)
    assert limiter.allow(uuid.uuid4())

    now[0] += 3601
    assert limiter.allow(USER)
