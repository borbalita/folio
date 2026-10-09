from __future__ import annotations

import base64

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from app.trace_export import (
    ContentFreeExporter,
    content_free,
    langfuse_otlp_exporter,
)


def _finished(
    name: str = "span",
    attributes: dict | None = None,
    *,
    exception: Exception | None = None,
    status: Status | None = None,
) -> ReadableSpan:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("test").start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_attributes(attributes or {})
        span.add_event("log", {"message": "SECRET-EVENT"})
        if exception is not None:
            span.record_exception(exception)
        if status is not None:
            span.set_status(status)
    (finished,) = exporter.get_finished_spans()
    return finished


def _everything(span: ReadableSpan) -> str:
    return repr(
        (
            dict(span.attributes or {}),
            [(event.name, dict(event.attributes or {})) for event in span.events],
            span.status.description,
        )
    )


def test_allowed_keys_and_metadata_survive() -> None:
    span = content_free(
        _finished(
            attributes={
                "gen_ai.request.model": "gpt-x",
                "gen_ai.usage.input_tokens": 5,
                "langfuse.observation.metadata.citation_count": 2,
                "user.id": "u",
            }
        )
    )

    assert dict(span.attributes or {}) == {
        "gen_ai.request.model": "gpt-x",
        "gen_ai.usage.input_tokens": 5,
        "langfuse.observation.metadata.citation_count": 2,
        "user.id": "u",
    }


def test_content_keys_are_dropped() -> None:
    span = content_free(
        _finished(
            attributes={
                "langfuse.observation.input": "SECRET",
                "langfuse.observation.output": "SECRET",
                "langfuse.observation.metadata.filters": '{"sender": "SECRET"}',
                "gen_ai.input.messages": "SECRET",
            }
        )
    )

    assert "SECRET" not in _everything(span)


def test_unknown_keys_are_dropped() -> None:
    original = _finished("plain", attributes={"foo.bar": "x"})

    span = content_free(original)

    assert "foo.bar" not in (span.attributes or {})
    assert span.name == "plain"
    assert span.context == original.context
    assert (span.start_time, span.end_time) == (original.start_time, original.end_time)


def test_exception_events_keep_only_the_type() -> None:
    span = content_free(_finished(exception=RuntimeError("SECRET")))

    assert [(e.name, dict(e.attributes or {})) for e in span.events] == [
        ("exception", {"exception.type": "RuntimeError"})
    ]


def test_status_description_is_the_exception_type_or_the_status_code() -> None:
    raised = content_free(
        _finished(
            exception=RuntimeError("SECRET"),
            status=Status(StatusCode.ERROR, "RuntimeError: SECRET"),
        )
    )
    coded = content_free(
        _finished(
            attributes={"langfuse.observation.status_message": "agent_run_failed"},
            status=Status(StatusCode.ERROR, "agent_run_failed"),
        )
    )
    other = content_free(_finished(status=Status(StatusCode.ERROR, "SECRET")))

    assert (raised.status.status_code, raised.status.description) == (
        StatusCode.ERROR,
        "RuntimeError",
    )
    assert coded.status.description == "agent_run_failed"
    assert other.status.status_code == StatusCode.ERROR
    assert other.status.description is None


def test_experiment_harness_spans_pass_unchanged() -> None:
    experiment = {"langfuse.experiment.item.id": "item-1"}
    harness = _finished(
        "experiment-item-run",
        attributes={**experiment, "langfuse.observation.input": "ITEM"},
    )
    child = _finished(
        "app-span", attributes={**experiment, "langfuse.observation.input": "ITEM"}
    )

    assert content_free(harness) is harness
    exported_child = content_free(child)
    assert "langfuse.observation.input" not in (exported_child.attributes or {})
    assert exported_child.attributes["langfuse.experiment.item.id"] == "item-1"


def test_exporter_filters_before_the_inner_exporter() -> None:
    inner = InMemorySpanExporter()

    ContentFreeExporter(inner).export([_finished(attributes={"foo": "SECRET"})])

    (exported,) = inner.get_finished_spans()
    assert "SECRET" not in _everything(exported)


def test_langfuse_otlp_exporter_matches_the_sdk() -> None:
    default = langfuse_otlp_exporter("pk", "sk", None)
    custom = langfuse_otlp_exporter("pk", "sk", "https://eu.example.com")

    assert default._endpoint == "https://cloud.langfuse.com/api/public/otel/v1/traces"
    assert custom._endpoint == "https://eu.example.com/api/public/otel/v1/traces"
    assert default._headers["Authorization"] == "Basic " + base64.b64encode(
        b"pk:sk"
    ).decode("ascii")
    assert default._headers["x-langfuse-public-key"] == "pk"
