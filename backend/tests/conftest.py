from __future__ import annotations

import functools
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from langfuse import Langfuse
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.auth.dependencies import CurrentUser, get_current_user
from app.main import app

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_THREAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def current_user() -> CurrentUser:
    return CurrentUser(id=TEST_USER_ID, email="test@example.com")


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(client: TestClient, current_user: CurrentUser) -> TestClient:
    async def override() -> CurrentUser:
        return current_user

    app.dependency_overrides[get_current_user] = override
    return client


@functools.cache
def _test_langfuse() -> tuple[Langfuse, InMemorySpanExporter]:
    # Langfuse caches its resources per public key, so one test client serves every test.
    # No ContentFreeExporter here: these spans show what the app itself records.
    exported = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-test",
        secret_key="sk-test",
        base_url="http://127.0.0.1:9",
        span_exporter=exported,
        tracer_provider=TracerProvider(),
    )
    return client, exported


@pytest.fixture
def langfuse_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[], tuple[ReadableSpan, ...]]:
    """The app's hand-made Langfuse observations, as recorded before export filtering."""
    client, exported = _test_langfuse()
    exported.clear()
    for module in (
        "app.chat.orchestrator",
        "app.retrieval.base",
        "app.retrieval.news.retriever",
        "app.retrieval.email.rerank",
    ):
        monkeypatch.setattr(f"{module}.get_client", lambda: client)

    def spans() -> tuple[ReadableSpan, ...]:
        client.flush()
        return exported.get_finished_spans()

    return spans


def span_text(spans: tuple[ReadableSpan, ...], name: str) -> str:
    """Everything a named span would export: attributes, events and status."""
    (span,) = [s for s in spans if s.name == name]
    return repr(
        (
            dict(span.attributes or {}),
            [(event.name, dict(event.attributes or {})) for event in span.events],
            span.status.description,
        )
    )
