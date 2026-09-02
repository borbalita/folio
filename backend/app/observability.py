"""Langfuse tracing setup for the PydanticAI document agent."""

from __future__ import annotations

import re

import structlog
from langfuse import Langfuse
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult, OtelSpanPatch
from pydantic_ai import Agent

from app.config import settings

log = structlog.get_logger(__name__)

_EMAIL_PATTERN = re.compile(r"\b[\w.-]+?@[\w.-]+?\.\w+?\b")


def _mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    """Redact email addresses from exported span attributes (e.g. an analyst pasting one into a question)."""
    patches: dict[object, OtelSpanPatch] = {}
    for identifier, span in params.spans.items():
        replacements: dict[str, str] = {}
        for key, value in span.attributes.items():
            if isinstance(value, str):
                masked = _EMAIL_PATTERN.sub("[REDACTED EMAIL]", value)
                if masked != value:
                    replacements[key] = masked
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    if not patches:
        return None
    return MaskOtelSpansResult(span_patches=patches)


def configure_tracing() -> None:
    """Initialize Langfuse + PydanticAI OTel instrumentation, if Langfuse keys are configured."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        log.info("tracing_disabled", reason="langfuse_keys_not_set")
        return

    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
        mask_otel_spans=_mask_otel_spans,
    )
    Agent.instrument_all()
    log.info("tracing_configured", environment=settings.environment)
