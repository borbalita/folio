"""Yahoo IMAP adapter. Returns parsed messages and does not touch the database."""

from __future__ import annotations

import imaplib
from dataclasses import dataclass
from datetime import date

from ingest.email.parse import ParsedMessage, parse_rfc822

IMAP_HOST = "imap.mail.yahoo.com"
IMAP_PORT = 993
FOLDER = "INBOX"


@dataclass(frozen=True, slots=True)
class FetchResult:
    messages: list[ParsedMessage]
    uidvalidity: int
    highest_uid: int | None


class YahooImapAdapter:
    def __init__(self, address: str, app_password: str) -> None:
        self._address = address
        self._app_password = app_password

    def fetch(self, *, limit: int, since: date | None) -> FetchResult:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(self._address, self._app_password)
            return fetch_inbox(imap, limit=limit, since=since)


def fetch_inbox(imap: imaplib.IMAP4, *, limit: int, since: date | None) -> FetchResult:
    status, _ = imap.select(FOLDER, readonly=True)
    if status != "OK":
        raise RuntimeError(f"Could not open {FOLDER}")
    uidvalidity = _uidvalidity(imap)
    criteria = "ALL" if since is None else f"(SINCE {since.strftime('%d-%b-%Y')})"
    status, data = imap.uid("SEARCH", criteria)
    if status != "OK" or not data or not data[0]:
        return FetchResult([], uidvalidity, None)
    uids = sorted((int(uid) for uid in data[0].split()), reverse=True)
    if limit > 0:
        uids = uids[:limit]
    messages: list[ParsedMessage] = []
    for uid in uids:
        status, fetched = imap.uid("FETCH", str(uid), "(RFC822)")
        if status != "OK" or not fetched or fetched[0] is None:
            continue
        raw = fetched[0][1]
        if not isinstance(raw, bytes):
            continue
        messages.append(parse_rfc822(raw, provider_message_id=str(uid), folder=FOLDER))
    highest = max(uids) if uids else None
    return FetchResult(messages, uidvalidity, highest)


def _uidvalidity(imap: imaplib.IMAP4) -> int:
    values = imap.untagged_responses.get("UIDVALIDITY", [])
    if not values:
        raise RuntimeError("IMAP server did not report UIDVALIDITY")
    return int(values[0])
