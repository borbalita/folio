"""Text for the search_emails tool response."""

from __future__ import annotations

from app.retrieval.email.retriever import EmailPassage


def format_email_passages(passages: list[EmailPassage]) -> str:
    if not passages:
        return "No matching mail."
    blocks = [
        "\n".join(
            [
                f"[{passage.chunk_id}]",
                f"From: {passage.from_address}",
                f"Subject: {passage.subject}",
                f"Date: {passage.sent_at.date().isoformat()}",
                f"Mailbox: {passage.mailbox_name}",
                passage.text,
            ]
        )
        for passage in passages
    ]
    return "\n\n".join(blocks)
