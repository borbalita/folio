"""Who can call you. A persona without a prompt file yet is listed but not callable."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).with_name("prompts")


@dataclass(frozen=True, slots=True)
class Persona:
    id: str
    name: str
    description: str
    voice: str
    available: bool

    def instructions(self) -> str:
        return (PROMPTS_DIR / f"{self.id}.md").read_text(encoding="utf-8")


PERSONAS: tuple[Persona, ...] = (
    Persona(
        id="friend",
        name="Friend",
        description="An old friend rings to catch up.",
        voice="marin",
        available=True,
    ),
    Persona(
        id="doctor",
        name="Doctor",
        description="A GP calls about how you've been feeling.",
        voice="cedar",
        available=False,
    ),
    Persona(
        id="interviewer",
        name="AI-job Interviewer",
        description="A recruiter screens you for an AI engineering role.",
        voice="ash",
        available=False,
    ),
)


def persona_by_id(persona_id: str) -> Persona | None:
    return next((persona for persona in PERSONAS if persona.id == persona_id), None)
