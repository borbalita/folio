from datetime import date

from ingest.email.yahoo import fetch_inbox


class _FakeImap:
    def __init__(self, uids: list[int], raw_by_uid: dict[int, bytes]) -> None:
        self.untagged_responses = {"UIDVALIDITY": [b"42"]}
        self._uids = uids
        self._raw = raw_by_uid
        self.searches: list[str] = []

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        assert folder == "INBOX"
        assert readonly is True
        return "OK", [b"3"]

    def uid(self, command: str, *args: str) -> tuple[str, list]:
        if command == "SEARCH":
            self.searches.append(args[0])
            payload = b" ".join(str(uid).encode() for uid in self._uids)
            return "OK", [payload]
        uid = int(args[0])
        return "OK", [(b"fetch", self._raw[uid])]


def test_fetch_inbox_caps_newest_and_records_cursor() -> None:
    raw = _raw("one@example.com")
    imap = _FakeImap([1, 9, 4], {9: raw, 4: raw, 1: raw})
    result = fetch_inbox(imap, limit=2, since=date(2026, 1, 15))
    assert imap.searches == ["(SINCE 15-Jan-2026)"]
    assert [message.provider_message_id for message in result.messages] == ["9", "4"]
    assert result.uidvalidity == 42
    assert result.highest_uid == 9


def test_fetch_inbox_limit_zero_returns_every_match() -> None:
    raw = _raw("one@example.com")
    imap = _FakeImap([2, 1], {1: raw, 2: raw})
    result = fetch_inbox(imap, limit=0, since=None)
    assert len(result.messages) == 2
    assert imap.searches == ["ALL"]


def _raw(message_id: str) -> bytes:
    return (
        f"Message-ID: <{message_id}>\r\n"
        "Subject: Hi\r\n"
        "From: a@example.com\r\n"
        "To: b@example.com\r\n"
        "Date: Fri, 02 Jan 2026 03:04:05 +0000\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Hello\r\n"
    ).encode()
