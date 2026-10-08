from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import jwt

from app.config import settings

BASE_URL = "https://api.enablebanking.com"
TIMEOUT_SECONDS = 30
JWT_LIFETIME = timedelta(hours=1)
CONSENT_DAYS = 180
# Request slightly under the 180-day maximum so clock skew can't push us over it.
CONSENT_MARGIN = timedelta(minutes=5)
COUNTRY = "DE"


class EnableBankingNotConfigured(Exception):
    pass


class EnableBankingError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Enable Banking returned {status}")
        self.status = status
        self.body = body


@dataclass(frozen=True)
class EbAccount:
    uid: str
    identification_hash: str
    iban: str | None
    name: str | None
    currency: str | None


@dataclass(frozen=True)
class EbSession:
    session_id: str
    valid_until: datetime
    accounts: list[EbAccount]


def sign_jwt(app_id: str, private_key_pem: str, now: datetime) -> str:
    claims = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": int(now.timestamp()),
        "exp": int((now + JWT_LIFETIME).timestamp()),
    }
    return jwt.encode(claims, private_key_pem, algorithm="RS256", headers={"kid": app_id})


def _auth_header() -> dict[str, str]:
    missing = [
        name
        for name, value in (
            ("ENABLE_BANKING_APP_ID", settings.enable_banking_app_id),
            ("ENABLE_BANKING_PRIVATE_KEY", settings.enable_banking_private_key),
            ("ENABLE_BANKING_REDIRECT_URL", settings.enable_banking_redirect_url),
        )
        if not value
    ]
    if missing:
        raise EnableBankingNotConfigured(
            f"Enable Banking is not configured: {', '.join(missing)} missing"
        )
    assert settings.enable_banking_app_id and settings.enable_banking_private_key
    token = sign_jwt(
        settings.enable_banking_app_id, settings.enable_banking_private_key, datetime.now(UTC)
    )
    return {"Authorization": f"Bearer {token}"}


async def _post(path: str, body: dict, client: httpx.AsyncClient | None) -> httpx.Response:
    headers = _auth_header()
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as owned:
                response = await owned.post(f"{BASE_URL}{path}", json=body, headers=headers)
        else:
            response = await client.post(f"{BASE_URL}{path}", json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise EnableBankingError(0, str(exc)) from exc
    if response.is_error:
        raise EnableBankingError(response.status_code, response.text)
    return response


async def start_authorization(
    bank: str, state: str, *, client: httpx.AsyncClient | None = None
) -> str:
    valid_until = datetime.now(UTC) + timedelta(days=CONSENT_DAYS) - CONSENT_MARGIN
    body = {
        "access": {"valid_until": valid_until.isoformat()},
        "aspsp": {"name": bank, "country": COUNTRY},
        "state": state,
        "redirect_url": settings.enable_banking_redirect_url,
        "psu_type": "personal",
    }
    response = await _post("/auth", body, client)
    try:
        return response.json()["url"]
    except (KeyError, ValueError, TypeError) as exc:
        raise EnableBankingError(response.status_code, "unexpected /auth response") from exc


async def create_session(code: str, *, client: httpx.AsyncClient | None = None) -> EbSession:
    response = await _post("/sessions", {"code": code}, client)
    try:
        data = response.json()
        accounts = [
            EbAccount(
                uid=account["uid"],
                identification_hash=account["identification_hash"],
                iban=(account.get("account_id") or {}).get("iban"),
                name=account.get("name"),
                currency=account.get("currency"),
            )
            for account in data["accounts"]
        ]
        return EbSession(
            session_id=data["session_id"],
            valid_until=datetime.fromisoformat(data["access"]["valid_until"]),
            accounts=accounts,
        )
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise EnableBankingError(response.status_code, "unexpected /sessions response") from exc
