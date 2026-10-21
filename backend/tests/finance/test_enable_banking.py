import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

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


def _entry(**overrides) -> dict:
    entry = {
        "entry_reference": None,
        "transaction_amount": {"currency": "EUR", "amount": "12.50"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "booking_date": "2026-10-01",
        "creditor": {"name": "Stadtwerke"},
        "creditor_account": {"iban": "DE89370400440532013000"},
        "debtor": {"name": "Owner"},
        "debtor_account": {"iban": "DE02120300000000202051"},
        "remittance_information": ["Rechnung 4711", "Kunde 42"],
        "bank_transaction_code": {"description": "Transfer", "code": "PMNT"},
    }
    entry.update(overrides)
    return entry


def test_fetch_follows_continuation_key(configured):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "continuation_key" not in request.url.params:
            return httpx.Response(
                200,
                json={"transactions": [_entry(entry_reference="a")], "continuation_key": "k2"},
            )
        return httpx.Response(200, json={"transactions": [_entry(entry_reference="b")]})

    result, unparsed = asyncio.run(
        enable_banking.fetch_transactions(
            "acc-1", date(2026, 7, 16), client=mock_client(handler)
        )
    )

    assert [t.entry_reference for t in result] == ["a", "b"]
    assert unparsed == 0
    assert requests[0].url.path == "/accounts/acc-1/transactions"
    assert requests[1].url.params["continuation_key"] == "k2"
    assert all(r.url.params["date_from"] == "2026-07-16" for r in requests)


def test_fetch_drops_pending_entries(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "transactions": [
                    _entry(entry_reference="booked"),
                    _entry(entry_reference="pending", status="PDNG"),
                    _entry(entry_reference="pending2", status="PEND"),
                ],
                "continuation_key": None,
            },
        )

    result, _ = asyncio.run(
        enable_banking.fetch_transactions(
            "acc-1", date(2026, 7, 16), client=mock_client(handler)
        )
    )

    assert [t.entry_reference for t in result] == ["booked"]


def test_parse_debit_is_negative_and_uses_creditor():
    tx = enable_banking.parse_transaction(_entry())

    assert tx is not None
    assert tx.amount == Decimal("-12.50")
    assert tx.direction == "DBIT"
    assert tx.currency == "EUR"
    assert tx.booking_date == date(2026, 10, 1)
    assert tx.counterparty_name == "Stadtwerke"
    assert tx.counterparty_iban == "DE89370400440532013000"
    assert tx.remittance == "Rechnung 4711\nKunde 42"
    assert tx.bank_code == "Transfer"


def test_parse_credit_uses_debtor():
    tx = enable_banking.parse_transaction(_entry(credit_debit_indicator="CRDT"))

    assert tx is not None
    assert tx.amount == Decimal("12.50")
    assert tx.counterparty_name == "Owner"
    assert tx.counterparty_iban == "DE02120300000000202051"


def test_parse_paypal_uses_transaction_date():
    entry = _entry(transaction_date="2026-09-30", creditor_account=None)
    del entry["booking_date"]

    tx = enable_banking.parse_transaction(entry)

    assert tx is not None
    assert tx.booking_date == date(2026, 9, 30)
    assert tx.counterparty_iban is None


def test_parse_unknown_indicator_raises():
    with pytest.raises(EnableBankingError):
        enable_banking.parse_transaction(_entry(credit_debit_indicator="XXXX"))


def test_fetch_sends_psu_headers_when_given(configured):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"transactions": []})

    asyncio.run(
        enable_banking.fetch_transactions(
            "acc-1",
            date(2026, 7, 16),
            psu_headers={"Psu-Ip-Address": "1.2.3.4", "Psu-User-Agent": "UA"},
            client=mock_client(handler),
        )
    )

    assert seen[0].headers["Psu-Ip-Address"] == "1.2.3.4"
    assert seen[0].headers["Psu-User-Agent"] == "UA"
    assert seen[0].headers["Authorization"].startswith("Bearer ")


def test_error_code_parsed_from_body() -> None:
    error = EnableBankingError(401, '{"code":401,"error":"EXPIRED_SESSION"}')

    assert error.code == "EXPIRED_SESSION"
    assert error.session_invalid


def test_aspsp_error_is_not_session_invalid() -> None:
    error = EnableBankingError(400, '{"code":400,"error":"ASPSP_ERROR"}')

    assert error.code == "ASPSP_ERROR"
    assert not error.session_invalid
    assert EnableBankingError(0, "connection reset").code is None
