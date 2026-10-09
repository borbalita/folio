"""Span export to Langfuse without content: only allowlisted attributes leave the process.

PydanticAI's instrumentation already runs with content off; this is the backstop for what
the source does not control — Langfuse SDK spans record exception messages and stack traces,
and a library upgrade may add new attributes.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence

from langfuse._version import __version__ as langfuse_version
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status

# Langfuse's experiment runner writes these; eval harness records may keep synthetic content.
HARNESS_SPANS = frozenset({"experiment-item-run", "experiment-item-task"})

ALLOWED_KEYS = frozenset(
    {
        # PydanticAI (gen_ai conventions)
        "gen_ai.operation.name",
        "gen_ai.system",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.response.model",
        "gen_ai.agent.name",
        "gen_ai.agent.call.id",
        "gen_ai.conversation.id",
        "gen_ai.tool.name",
        "gen_ai.tool.call.id",
        "agent_name",
        "model_name",
        # Langfuse
        "user.id",
        "session.id",
        "langfuse.environment",
        "langfuse.trace.name",
        "langfuse.trace.tags",
        "langfuse.observation.type",
        "langfuse.observation.level",
        "langfuse.observation.status_message",
        "langfuse.observation.model.name",
        "langfuse.observation.usage_details",
        "langfuse.internal.is_app_root",
        "langfuse.internal.as_root",
        "langfuse.experiment.id",
        "langfuse.experiment.name",
        "langfuse.experiment.item.id",
        "langfuse.experiment.item.root_observation_id",
        "langfuse.experiment.dataset.id",
    }
)
ALLOWED_PREFIXES = ("gen_ai.usage.", "gen_ai.aggregated_usage.")
ALLOWED_METADATA = frozenset(
    {
        "citation_count",
        "insufficient_evidence",
        "retrieved_chunk_count",
        "grounding_failure_code",
        "passage_count",
        "corpus",
        "candidate_k",
        "top_k",
        "rrf_k",
        "model",
        "candidates",
        "kept",
        "dropped",
        "failed",
    }
)
_METADATA_PREFIX = "langfuse.observation.metadata."
_STATUS_MESSAGE = "langfuse.observation.status_message"


def _allowed(key: str) -> bool:
    if key.startswith(_METADATA_PREFIX):
        return key.removeprefix(_METADATA_PREFIX) in ALLOWED_METADATA
    return key in ALLOWED_KEYS or key.startswith(ALLOWED_PREFIXES)


def content_free(span: ReadableSpan) -> ReadableSpan:
    """The span rebuilt from allowlisted attributes, exception types and status codes."""
    if span.name in HARNESS_SPANS:
        return span
    attributes = {k: v for k, v in (span.attributes or {}).items() if _allowed(k)}
    exceptions = [
        Event(
            "exception",
            {"exception.type": str((event.attributes or {}).get("exception.type"))},
            event.timestamp,
        )
        for event in span.events
        if event.name == "exception"
    ]
    if exceptions:
        description = exceptions[-1].attributes["exception.type"]
    else:
        description = attributes.get(_STATUS_MESSAGE)
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=exceptions,
        links=(),
        kind=span.kind,
        status=Status(span.status.status_code, description),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class ContentFreeExporter(SpanExporter):
    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([content_free(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def langfuse_otlp_exporter(
    public_key: str, secret_key: str, base_url: str | None
) -> OTLPSpanExporter:
    """The exporter Langfuse would build itself (langfuse/_client/span_processor.py)."""
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode("ascii")
    return OTLPSpanExporter(
        endpoint=f"{base_url or 'https://cloud.langfuse.com'}/api/public/otel/v1/traces",
        headers={
            "Authorization": f"Basic {auth}",
            "x-langfuse-sdk-name": "python",
            "x-langfuse-sdk-version": langfuse_version,
            "x-langfuse-public-key": public_key,
        },
    )
