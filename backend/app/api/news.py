"""AI News dashboard routes, for users with a news mailbox."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.email_access import require_news_access
from app.config import settings
from app.database import news_feed

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/stories")
async def list_stories(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    before: date | None = None,
    days: Annotated[int, Query(ge=1, le=60)] = 14,
    only: Literal["big"] | None = None,
) -> dict[str, Any]:
    """Stories on the `days` days before `before` (default: through today), newest day first."""
    mailbox_ids = await require_news_access(user)
    if before is None:
        before = datetime.now(ZoneInfo(settings.email_timezone)).date() + timedelta(days=1)
    return await asyncio.to_thread(
        news_feed.list_stories, mailbox_ids, before=before, days=days, only_big=only == "big"
    )
