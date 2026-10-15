from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import jwt
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

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
class EbTransaction:
    booking_date: date
    amount: Decimal  # negative for debits
    currency: str
    direction: str  # CRDT or DBIT
    entry_reference: str | None
    counterparty_name: str | None
    counterparty_iban: str | None
    remittance: str
    bank_code: str | None
    raw: dict


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


async def _send(
    method: str,
    path: str,
    client: httpx.AsyncClient | None,
    *,
    extra_headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    headers = {**(extra_headers or {}), **_auth_header()}
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as owned:
                response = await owned.request(
                    method, f"{BASE_URL}{path}", headers=headers, **kwargs
                )
        else:
            response = await client.request(
                method, f"{BASE_URL}{path}", headers=headers, **kwargs
            )
    except httpx.HTTPError as exc:
        raise EnableBankingError(0, str(exc)) from exc
    if response.is_error:
        raise EnableBankingError(response.status_code, response.text)
    return response


async def _post(path: str, body: dict, client: httpx.AsyncClient | None) -> httpx.Response:
    return await _send("POST", path, client, json=body)


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


def parse_transaction(entry: dict) -> EbTransaction | None:
    """None for anything not booked; pending entries can be dated in the future."""
    try:
        if entry["status"] != "BOOK":
            return None
        direction = entry["credit_debit_indicator"]
        if direction not in ("CRDT", "DBIT"):
            raise ValueError(f"credit_debit_indicator {direction!r}")
        amount = Decimal(entry["transaction_amount"]["amount"])
        party, account = (
            ("creditor", "creditor_account")
            if direction == "DBIT"
            else ("debtor", "debtor_account")
        )
        # PayPal sends only transaction_date.
        booked = entry.get("booking_date") or entry["transaction_date"]
        code = entry.get("bank_transaction_code") or {}
        return EbTransaction(
            booking_date=date.fromisoformat(booked),
            amount=-abs(amount) if direction == "DBIT" else abs(amount),
            currency=entry["transaction_amount"]["currency"],
            direction=direction,
            entry_reference=entry.get("entry_reference") or None,
            counterparty_name=(entry.get(party) or {}).get("name"),
            counterparty_iban=(entry.get(account) or {}).get("iban"),
            remittance="\n".join(entry.get("remittance_information") or []),
            bank_code=code.get("description") or code.get("code"),
            raw=entry,
        )
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation) as exc:
        raise EnableBankingError(200, "unexpected transaction") from exc


def parse_page(entries: list[dict]) -> tuple[list[EbTransaction], int]:
    """Booked transactions, and how many entries could not be read.

    One unreadable entry is skipped rather than failing the account: it would
    otherwise be re-read, and fail, on every sync.
    """
    parsed: list[EbTransaction] = []
    unparsed = 0
    for entry in entries:
        try:
            tx = parse_transaction(entry)
        except EnableBankingError as exc:
            unparsed += 1
            # The cause's type only: its message can carry transaction content.
            log.warning("bank_transaction_unparsed", cause=type(exc.__cause__).__name__)
            continue
        if tx is not None:
            parsed.append(tx)
    return parsed, unparsed


async def fetch_transactions(
    account_uid: str,
    date_from: date,
    *,
    psu_headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[list[EbTransaction], int]:
    """Every booked transaction since `date_from` across all pages, and the unreadable count."""
    result: list[EbTransaction] = []
    unparsed = 0
    params = {"date_from": date_from.isoformat()}
    while True:
        response = await _send(
            "GET",
            f"/accounts/{account_uid}/transactions",
            client,
            extra_headers=psu_headers,
            params=params,
        )
        try:
            data = response.json()
            entries = data["transactions"]
        except (KeyError, ValueError, TypeError) as exc:
            raise EnableBankingError(
                response.status_code, "unexpected /transactions response"
            ) from exc
        parsed, skipped = parse_page(entries)
        result.extend(parsed)
        unparsed += skipped
        key = data.get("continuation_key")
        if not key:
            return result, unparsed
        params = {"date_from": date_from.isoformat(), "continuation_key": key}
