import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings, settings
from app.finance import enable_banking
from app.finance.enable_banking import (
    EnableBankingError,
    EnableBankingNotConfigured,
    create_session,
    sign_jwt,
    start_authorization,
)

REDIRECT_URL = "http://localhost:5173/finance/accounts/callback"


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def pem(rsa_key: rsa.RSAPrivateKey) -> str:
    return rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch, pem: str) -> None:
    monkeypatch.setattr(settings, "enable_banking_app_id", "app-123")
    monkeypatch.setattr(settings, "enable_banking_private_key", pem)
    monkeypatch.setattr(settings, "enable_banking_redirect_url", REDIRECT_URL)


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_jwt_header_and_claims_match_enable_banking(rsa_key, pem):
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)

    token = sign_jwt("app-123", pem, now)

    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == "app-123"
    claims = jwt.decode(
        token,
        rsa_key.public_key(),
        audience="api.enablebanking.com",
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["iss"] == "enablebanking.com"
    assert claims["aud"] == "api.enablebanking.com"
    assert claims["iat"] == int(now.timestamp())
    assert 0 < claims["exp"] - claims["iat"] <= 86400


def test_private_key_with_literal_newlines_is_normalised(pem):
    built = Settings(
        _env_file=None,
        supabase_url="x",
        supabase_anon_key="x",
        supabase_service_role_key="x",
        database_url="x",
        openai_api_key="x",
        openai_chat_model="x",
        openai_embedding_model="x",
        openai_embedding_dimensions=1,
        allowed_origins="http://localhost",
        email_rerank=False,
        enable_banking_private_key=pem.strip().replace("\n", "\\n"),
    )

    assert built.enable_banking_private_key is not None
    assert sign_jwt("app-123", built.enable_banking_private_key, datetime.now(UTC))


def test_start_authorization_without_app_id_names_the_setting(monkeypatch, configured):
    monkeypatch.setattr(settings, "enable_banking_app_id", None)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"url": "x"})

    async def run() -> None:
        async with mock_client(handler) as client:
            await start_authorization("N26", "state-1", client=client)

    with pytest.raises(EnableBankingNotConfigured, match="ENABLE_BANKING_APP_ID"):
        asyncio.run(run())
    assert requests == []


def test_start_authorization_sends_bank_state_and_redirect(configured):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"url": "https://bank.example/x"})

    async def run() -> str:
        async with mock_client(handler) as client:
            return await start_authorization("N26", "state-1", client=client)

    assert asyncio.run(run()) == "https://bank.example/x"

    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/auth"
    token = request.headers["authorization"].removeprefix("Bearer ")
    assert jwt.get_unverified_header(token)["kid"] == "app-123"
    body = json.loads(request.content)
    assert body["aspsp"] == {"name": "N26", "country": "DE"}
    assert body["state"] == "state-1"
    assert body["redirect_url"] == REDIRECT_URL
    assert body["psu_type"] == "personal"
    valid_until = datetime.fromisoformat(body["access"]["valid_until"])
    expected = datetime.now(UTC) + timedelta(days=180, minutes=-5)
    assert abs(valid_until - expected) < timedelta(minutes=1)


def test_create_session_parses_accounts(configured):
    payload = {
        "session_id": "sess-1",
        "access": {"valid_until": "2027-04-06T10:00:00+00:00"},
        "accounts": [
            {
                "uid": "uid-1",
                "identification_hash": "hash-1",
                "account_id": {"iban": "DE89370400440532013000"},
                "name": "Main",
                "currency": "EUR",
            },
            {"uid": "uid-2", "identification_hash": "hash-2"},
        ],
    }
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    async def run() -> enable_banking.EbSession:
        async with mock_client(handler) as client:
            return await create_session("code-1", client=client)

    session = asyncio.run(run())

    assert seen[0].url.path == "/sessions"
    assert json.loads(seen[0].content) == {"code": "code-1"}
    assert session.session_id == "sess-1"
    assert session.valid_until == datetime(2027, 4, 6, 10, 0, tzinfo=UTC)
    assert session.accounts == [
        enable_banking.EbAccount("uid-1", "hash-1", "DE89370400440532013000", "Main", "EUR"),
        enable_banking.EbAccount("uid-2", "hash-2", None, None, None),
    ]


def test_network_failure_becomes_enable_banking_error(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async def run() -> str:
        async with mock_client(handler) as client:
            return await start_authorization("N26", "state-1", client=client)

    with pytest.raises(EnableBankingError) as caught:
        asyncio.run(run())
    assert caught.value.status == 0
    assert "boom" in caught.value.body


def test_unexpected_auth_payload_becomes_enable_banking_error(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async def run() -> str:
        async with mock_client(handler) as client:
            return await start_authorization("N26", "state-1", client=client)

    with pytest.raises(EnableBankingError) as caught:
        asyncio.run(run())
    assert caught.value.status == 200


def test_unexpected_sessions_payload_becomes_enable_banking_error(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    async def run() -> enable_banking.EbSession:
        async with mock_client(handler) as client:
            return await create_session("code-1", client=client)

    with pytest.raises(EnableBankingError):
        asyncio.run(run())


def test_error_response_raises_enable_banking_error(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    async def run() -> None:
        async with mock_client(handler) as client:
            await create_session("bad", client=client)

    with pytest.raises(EnableBankingError) as exc:
        asyncio.run(run())
    assert exc.value.status == 400
    assert "invalid_grant" in exc.value.body
