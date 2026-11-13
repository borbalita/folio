from __future__ import annotations

import uuid

import pytest

from app.config import settings
from app.phone.personas import PERSONAS, persona_by_id
from app.phone.session import CallLimiter, max_seconds, session_config

USER = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def test_every_persona_can_be_called() -> None:
    assert [persona.id for persona in PERSONAS if persona.available] == [
        "friend",
        "doctor",
        "interviewer",
    ]


@pytest.mark.parametrize(
    ("persona_id", "keyword"),
    [("friend", "friend"), ("doctor", "doctor"), ("interviewer", "interview")],
)
def test_each_session_has_its_own_prompt_voice_and_transcription(
    persona_id: str, keyword: str
) -> None:
    persona = persona_by_id(persona_id)
    assert persona is not None

    config = session_config(persona)

    assert config["type"] == "realtime"
    assert config["model"] == settings.openai_realtime_model
    assert config["instructions"] == persona.instructions()
    assert keyword in config["instructions"].lower()
    assert config["audio"]["output"]["voice"] == persona.voice
    assert (
        config["audio"]["input"]["transcription"]["model"]
        == settings.openai_realtime_transcribe_model
    )


def test_voices_differ_between_personas() -> None:
    assert len({persona.voice for persona in PERSONAS}) == len(PERSONAS)


def test_doctor_prompt_keeps_the_safety_rules() -> None:
    doctor = persona_by_id("doctor")
    assert doctor is not None
    prompt = doctor.instructions().lower()

    assert "diagnos" in prompt
    assert "prescri" in prompt
    assert "112" in prompt


def test_interviewer_gets_a_longer_call_than_the_default() -> None:
    interviewer = persona_by_id("interviewer")
    friend = persona_by_id("friend")
    assert interviewer is not None and friend is not None

    assert max_seconds(interviewer) == 600
    assert max_seconds(friend) == settings.phone_call_max_seconds


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
