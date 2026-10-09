from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import observability
from app.trace_export import ContentFreeExporter


@pytest.fixture
def exported() -> Iterator[InMemorySpanExporter]:
    inner = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ContentFreeExporter(inner)))
    Agent.instrument_all(observability.content_free_instrumentation(provider))
    yield inner
    Agent.instrument_all(False)


def _everything(exporter: InMemorySpanExporter) -> str:
    return repr(
        [
            (
                dict(span.attributes or {}),
                [(event.name, dict(event.attributes or {})) for event in span.events],
                span.status.description,
            )
            for span in exporter.get_finished_spans()
        ]
    )


def _searching_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("search", {"query": "SECRET-QUERY"})])
    return ModelResponse(parts=[TextPart("SECRET-ANSWER")])


def test_agent_run_exports_shape_not_content(exported: InMemorySpanExporter) -> None:
    agent = Agent(FunctionModel(_searching_model), instructions="SECRET-INSTR")

    @agent.tool_plain
    def search(query: str) -> str:
        return "SECRET-RESULT"

    agent.run_sync(
        [
            "SECRET-USER",
            BinaryContent(data=b"%PDF-SECRET", media_type="application/pdf"),
        ]
    )

    everything = _everything(exported)
    assert "SECRET-" not in everything
    assert "PDF" not in everything
    attributes = [dict(s.attributes or {}) for s in exported.get_finished_spans()]
    assert any("gen_ai.request.model" in a for a in attributes)
    assert any("gen_ai.usage.input_tokens" in a for a in attributes)
    assert any(a.get("gen_ai.tool.name") == "search" for a in attributes)


def test_failing_agent_exports_the_type_only(exported: InMemorySpanExporter) -> None:
    def fail(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ValueError("SECRET-ERROR")

    with pytest.raises(ValueError):
        Agent(FunctionModel(fail)).run_sync("hello")

    assert "SECRET-ERROR" not in _everything(exported)
    exception_events = [
        dict(event.attributes or {})
        for span in exported.get_finished_spans()
        for event in span.events
    ]
    assert exception_events
    assert all(e == {"exception.type": "ValueError"} for e in exception_events)


def test_configure_tracing_uses_content_free_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    langfuse_kwargs: dict[str, Any] = {}
    instrumented: list[Any] = []
    monkeypatch.setattr(observability.settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(observability.settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(observability.trace, "set_tracer_provider", lambda _: None)
    monkeypatch.setattr(
        observability, "Langfuse", lambda **kwargs: langfuse_kwargs.update(kwargs)
    )
    monkeypatch.setattr(observability.Agent, "instrument_all", instrumented.append)

    observability.configure_tracing()

    (settings,) = instrumented
    assert settings.include_content is False
    assert settings.include_binary_content is False
    assert isinstance(langfuse_kwargs["span_exporter"], ContentFreeExporter)
    assert "mask_otel_spans" not in langfuse_kwargs


# Every attribute key a content-free PydanticAI 2.46 run records, allowlisted or not.
# A library upgrade that changes this set fails here, so the allowlist is revisited.
PYDANTIC_AI_KEYS = {
    "agent_name",
    "gen_ai.agent.call.id",
    "gen_ai.agent.name",
    "gen_ai.aggregated_usage.input_tokens",
    "gen_ai.aggregated_usage.output_tokens",
    "gen_ai.conversation.id",
    "gen_ai.input.messages",
    "gen_ai.operation.name",
    "gen_ai.output.messages",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.system",
    "gen_ai.tool.call.id",
    "gen_ai.tool.definitions",
    "gen_ai.tool.name",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "logfire.json_schema",
    "logfire.msg",
    "model_name",
    "model_request_parameters",
    "pydantic_ai.all_messages",
}


@pytest.fixture
def recorded() -> Iterator[InMemorySpanExporter]:
    """PydanticAI spans as recorded at the source, before any export filtering."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    Agent.instrument_all(observability.content_free_instrumentation(provider))
    yield exporter
    Agent.instrument_all(False)


def _run_search_agent() -> None:
    agent = Agent(FunctionModel(_searching_model), instructions="SECRET-INSTR")

    @agent.tool_plain
    def search(query: str) -> str:
        return "SECRET-RESULT"

    agent.run_sync(
        [
            "SECRET-USER",
            BinaryContent(data=b"%PDF-SECRET", media_type="application/pdf"),
        ]
    )


def test_agent_run_records_no_content_or_file_at_the_source(
    recorded: InMemorySpanExporter,
) -> None:
    _run_search_agent()

    everything = _everything(recorded)
    assert "SECRET-" not in everything
    assert "%PDF" not in everything
    assert "JVBER" not in everything  # base64 of "%PDF"


def test_recorded_keys_match_the_known_set(recorded: InMemorySpanExporter) -> None:
    _run_search_agent()

    keys = {key for s in recorded.get_finished_spans() for key in s.attributes or {}}
    assert keys == PYDANTIC_AI_KEYS
