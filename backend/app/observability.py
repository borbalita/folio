"""Langfuse tracing for every agent, without content: shape, models, tokens, timings and error types."""

from __future__ import annotations

import structlog
from langfuse import Langfuse, get_client
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings

from app.config import settings
from app.trace_export import ContentFreeExporter, langfuse_otlp_exporter

log = structlog.get_logger(__name__)

_SERVICE_NAME = "document-copilot-backend"


def content_free_instrumentation(
    tracer_provider: TracerProvider | None = None,
) -> InstrumentationSettings:
    """PydanticAI spans without prompts, instructions, outputs, tool arguments or results, or files."""
    return InstrumentationSettings(
        include_content=False,
        include_binary_content=False,
        tracer_provider=tracer_provider,
    )


def configure_tracing() -> None:
    """Initialize content-free Langfuse export and PydanticAI instrumentation, if Langfuse keys are configured."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        log.info("tracing_disabled", reason="langfuse_keys_not_set")
        return

    # Register our own provider as the OTel *global* default before Langfuse attaches
    # its exporter to it — PydanticAI's instrumentation reads the global provider, so
    # if Langfuse only wired up the instance we hand it, agent spans would go nowhere.
    provider = TracerProvider(resource=Resource.create({"service.name": _SERVICE_NAME}))
    trace.set_tracer_provider(provider)

    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
        span_exporter=ContentFreeExporter(
            langfuse_otlp_exporter(
                settings.langfuse_public_key,
                settings.langfuse_secret_key,
                settings.langfuse_base_url,
            )
        ),
        tracer_provider=provider,
    )
    Agent.instrument_all(content_free_instrumentation())
    log.info("tracing_configured", environment=settings.environment)


def shutdown_tracing() -> None:
    """Flush buffered spans before the process exits (e.g. on a Railway SIGTERM)."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return
    get_client().shutdown()
