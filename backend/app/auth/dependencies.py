"""FastAPI dependencies for Supabase JWT authentication."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient
from supabase.lib.client_options import AsyncClientOptions
from supabase_auth.errors import AuthApiError

from app.config import settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str


@lru_cache(maxsize=1)
def _auth_client() -> AsyncClient:
    """Shared anon client for JWT verification. Tokens are passed to get_user explicitly."""
    return AsyncClient(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=AsyncClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    token = credentials.credentials.strip()
    if not token:
        raise _unauthorized()

    return token


async def get_current_user(
    access_token: Annotated[str, Depends(get_access_token)],
) -> CurrentUser:
    try:
        response = await _auth_client().auth.get_user(jwt=access_token)
    except AuthApiError as exc:
        raise _unauthorized("Invalid or expired token") from exc

    if response is None or response.user is None or not response.user.email:
        raise _unauthorized("Invalid or expired token")

    return CurrentUser(
        id=uuid.UUID(str(response.user.id)),
        email=response.user.email,
    )
