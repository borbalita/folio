"""Phone agent routes: the persona list and a Realtime secret for one call."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.phone_access import require_phone_user
from app.config import settings
from app.phone import session
from app.phone.personas import PERSONAS, persona_by_id
from app.phone.session import CallLimiter

router = APIRouter(prefix="/phone", tags=["phone"])


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PersonaOut(CamelModel):
    id: str
    name: str
    description: str
    available: bool


class SessionRequest(BaseModel):
    persona: str


class SessionOut(CamelModel):
    secret: str
    expires_at: int
    max_seconds: int


def get_call_limiter(request: Request) -> CallLimiter:
    return request.app.state.phone_call_limiter


@router.get("/personas", response_model_by_alias=True)
async def list_personas(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[PersonaOut]:
    require_phone_user(user)
    return [
        PersonaOut(
            id=p.id, name=p.name, description=p.description, available=p.available
        )
        for p in PERSONAS
    ]


@router.post("/session", response_model_by_alias=True)
async def create_session(
    body: SessionRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    limiter: Annotated[CallLimiter, Depends(get_call_limiter)],
) -> SessionOut:
    require_phone_user(user)
    persona = persona_by_id(body.persona)
    if persona is None or not persona.available:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not limiter.allow(user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="That's a lot of calls for one hour. Try again later.",
        )
    secret = await session.create_call_secret(persona)
    return SessionOut(
        secret=secret.secret,
        expires_at=secret.expires_at,
        max_seconds=settings.phone_call_max_seconds,
    )
