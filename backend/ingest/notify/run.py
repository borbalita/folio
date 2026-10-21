"""Telegram setup helper. Run from backend/: uv run python -m ingest.notify --chat-id"""

from __future__ import annotations

import argparse
import sys

import httpx

from app.config import settings
from app.notifications.telegram import API_URL, TIMEOUT_SECONDS

TEST_TEXT = "✅ Folio notifications are set up."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram notification setup")
    parser.add_argument(
        "--chat-id",
        action="store_true",
        help="Print the chats that messaged the bot, to set TELEGRAM_CHAT_ID",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a test message to TELEGRAM_CHAT_ID",
    )
    return parser


class TelegramRefused(Exception):
    """Telegram answered with an error. The message never holds the request URL: it contains
    the bot token."""


def chat_ids(client: httpx.Client) -> list[str]:
    try:
        response = client.get(f"{API_URL}/bot{settings.telegram_bot_token}/getUpdates")
    except httpx.HTTPError as exc:
        raise TelegramRefused(f"Could not reach Telegram ({type(exc).__name__}).") from None
    if response.status_code != 200:
        raise TelegramRefused(f"Telegram answered {response.status_code}; check the token.")
    seen: dict[int, str] = {}
    for update in response.json().get("result", []):
        chat = (update.get("message") or {}).get("chat") or {}
        if "id" in chat:
            name = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
            seen[chat["id"]] = f"{chat['id']}  {name} ({chat.get('type', '?')})"
    return list(seen.values())


def main(argv: list[str] | None = None, *, client: httpx.Client | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.chat_id or args.test):
        build_parser().print_help()
        return 1
    if not settings.telegram_bot_token:
        print("Set TELEGRAM_BOT_TOKEN in backend/.env first.", file=sys.stderr)
        return 1
    if args.test:
        if not settings.telegram_chat_id:
            print("Set TELEGRAM_CHAT_ID in backend/.env first.", file=sys.stderr)
            return 1
        try:
            with client or httpx.Client(timeout=TIMEOUT_SECONDS) as http:
                response = http.post(
                    f"{API_URL}/bot{settings.telegram_bot_token}/sendMessage",
                    json={"chat_id": settings.telegram_chat_id, "text": TEST_TEXT},
                )
        except httpx.HTTPError as exc:
            print(f"Could not reach Telegram ({type(exc).__name__}).", file=sys.stderr)
            return 1
        if response.status_code != 200:
            print(f"Telegram answered {response.status_code}.", file=sys.stderr)
            return 1
        print("Sent. Check Telegram.")
        return 0
    try:
        with client or httpx.Client(timeout=TIMEOUT_SECONDS) as http:
            found = chat_ids(http)
    except TelegramRefused as exc:
        print(exc, file=sys.stderr)
        return 1
    if not found:
        print(
            "No chats yet. Send your bot a message in Telegram, then run this again.",
            file=sys.stderr,
        )
        return 1
    print("\n".join(found))
    return 0
