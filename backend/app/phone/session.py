"""Short-lived OpenAI Realtime secrets the browser uses to place a call itself."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.phone.personas import Persona

HOUR_SECONDS = 3600
# The browser uses the secret right away; the call itself may run longer.
SECRET_TTL_SECONDS = 60


@dataclass(frozen=True, slots=True)
class CallSecret:
    secret: str
    expires_at: int


class CallLimiter:
    """Calls started per user in the last hour, in memory: a restart forgets them."""

    def __init__(
        self, per_hour: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._per_hour = per_hour
        self._clock = clock
        self._starts: defaultdict[uuid.UUID, deque[float]] = defaultdict(deque)

    def allow(self, user_id: uuid.UUID) -> bool:
        now = self._clock()
        starts = self._starts[user_id]
        while starts and now - starts[0] >= HOUR_SECONDS:
            starts.popleft()
        if len(starts) >= self._per_hour:
            return False
        starts.append(now)
        return True


@lru_cache(maxsize=1)
def realtime_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def session_config(persona: Persona) -> dict[str, Any]:
    return {
        "type": "realtime",
        "model": settings.openai_realtime_model,
        "instructions": persona.instructions(),
        "audio": {
            "input": {
                "transcription": {"model": settings.openai_realtime_transcribe_model},
                "turn_detection": {"type": "server_vad"},
            },
            "output": {"voice": persona.voice},
        },
    }


async def create_call_secret(persona: Persona) -> CallSecret:
    response = await realtime_client().realtime.client_secrets.create(
        expires_after={"anchor": "created_at", "seconds": SECRET_TTL_SECONDS},
        session=session_config(persona),  # type: ignore[arg-type]
    )
    return CallSecret(secret=response.value, expires_at=response.expires_at)
