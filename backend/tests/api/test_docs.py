from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import docs_urls


def test_production_does_not_serve_api_docs() -> None:
    client = TestClient(FastAPI(**docs_urls("production")))

    for path in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(path).status_code == 404


def test_local_serves_api_docs(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200
