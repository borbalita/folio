from typing import Annotated

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.auth.dependencies import CurrentUser, get_current_user
from app.config import settings
from app.logging import configure_logging

configure_logging()
log = structlog.get_logger(__name__)

app = FastAPI(title="Document Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-vercel-ai-ui-message-stream"],
)

app.include_router(chat_router)


@app.on_event("startup")
async def on_startup() -> None:
    log.info("application_started", title=app.title)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
async def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    return user


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
