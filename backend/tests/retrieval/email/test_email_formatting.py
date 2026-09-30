from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.retrieval.email.formatting import format_email_passages
from app.retrieval.email.retriever import EmailPassage

CHUNK = UUID("00000000-0000-0000-0000-0000000000aa")


def test_empty_passages() -> None:
    assert format_email_passages([]) == "No matching mail."


def test_passage_lists_chunk_id_sender_subject_date_and_mailbox() -> None:
    output = format_email_passages(
        [
            EmailPassage(
                chunk_id=CHUNK,
                email_id=UUID("00000000-0000-0000-0000-0000000000bb"),
                text="Rent is due Friday.",
                from_address="landlord@example.com",
                subject="September rent",
                sent_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
                mailbox_name="Yahoo",
                fusion_score=0.1,
            )
        ]
    )

    assert f"[{CHUNK}]" in output
    assert "From: landlord@example.com" in output
    assert "Subject: September rent" in output
    assert "Date: 2026-09-04" in output
    assert "Mailbox: Yahoo" in output
    assert output.endswith("Rent is due Friday.")
