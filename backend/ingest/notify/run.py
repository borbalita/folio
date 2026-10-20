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


def chat_ids(client: httpx.Client) -> list[str]:
    response = client.get(f"{API_URL}/bot{settings.telegram_bot_token}/getUpdates")
    response.raise_for_status()
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
        with client or httpx.Client(timeout=TIMEOUT_SECONDS) as http:
            response = http.post(
                f"{API_URL}/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id, "text": TEST_TEXT},
            )
        if response.status_code != 200:
            print(f"Telegram answered {response.status_code}.", file=sys.stderr)
            return 1
        print("Sent. Check Telegram.")
        return 0
    with client or httpx.Client(timeout=TIMEOUT_SECONDS) as http:
        found = chat_ids(http)
    if not found:
        print(
            "No chats yet. Send your bot a message in Telegram, then run this again.",
            file=sys.stderr,
        )
        return 1
    print("\n".join(found))
    return 0
