import uuid
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    openai_api_key: str
    openai_chat_model: str
    openai_embedding_model: str
    openai_embedding_dimensions: int = Field(gt=0)
    allowed_origins: Annotated[list[str], NoDecode]
    log_level: LogLevel = "INFO"
    retrieval_candidate_k: int = Field(default=50, gt=0)
    retrieval_top_k: int = Field(default=10, gt=0)
    retrieval_rrf_k: int = Field(default=60, gt=0)
    retrieval_neighbor_radius: int = Field(default=1, ge=0)
    retrieval_fts_config: str = "english"
    environment: Literal["local", "production"] = "local"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None
    yahoo_email: str | None = None
    yahoo_app_password: str | None = None
    email_agent_owner_user_id: uuid.UUID | None = None
    typesafe_api_key: str | None = None
    typesafe_label_model: str = "jev-latest"
    email_rerank: bool = True
    email_rerank_candidates: int = Field(default=20, gt=0)
    attachment_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    email_timezone: str = "Europe/Berlin"
    news_match_window_hours: int = Field(default=48, gt=0)
    ai_newsletter_domains: Annotated[dict[str, str], NoDecode] = {}

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def rerank_needs_typesafe(self) -> "Settings":
        if self.email_rerank and not self.typesafe_api_key:
            raise ValueError(
                "EMAIL_RERANK needs TYPESAFE_API_KEY; set it or EMAIL_RERANK=false"
            )
        return self

    @field_validator("email_timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator(
        "yahoo_email", "yahoo_app_password", "typesafe_api_key", mode="before"
    )
    @classmethod
    def blank_optional_str(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    @field_validator("email_agent_owner_user_id", mode="before")
    @classmethod
    def blank_optional_uuid(
        cls, value: str | uuid.UUID | None
    ) -> str | uuid.UUID | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("ai_newsletter_domains", mode="before")
    @classmethod
    def parse_newsletter_domains(cls, value: object) -> dict[str, str]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {
                str(key).strip().lower(): str(item).strip()
                for key, item in value.items()
            }
        mapping: dict[str, str] = {}
        for part in str(value).split(","):
            if "=" not in part:
                continue
            sender, source = part.split("=", 1)
            sender = sender.strip().lower()
            source = source.strip()
            if sender and source:
                mapping[sender] = source
        return mapping


settings = Settings()
