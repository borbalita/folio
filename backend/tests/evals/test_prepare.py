from __future__ import annotations

from uuid import UUID

from evals.emails import message_id
from evals.prepare import LabelMismatch, group_stored_rows, label_mismatches

EMAIL_1 = UUID("00000000-0000-0000-0000-000000000001")
EMAIL_2 = UUID("00000000-0000-0000-0000-000000000002")
CHUNKS = [UUID(f"00000000-0000-0000-0000-0000000000c{n}") for n in range(3)]


def test_label_mismatches_list_wrong_and_missing_labels_by_key() -> None:
    expected = {"e01": "invoice", "e02": "other", "e03": "promotional"}
    stored = {"e01": "invoice", "e02": "needs_reply"}

    assert label_mismatches(expected, stored) == [
        LabelMismatch(email_key="e02", expected="other", stored="needs_reply"),
        LabelMismatch(email_key="e03", expected="promotional", stored=None),
    ]


def test_stored_rows_group_into_one_entry_per_email_with_chunks_in_order() -> None:
    rows = [
        (message_id("e01"), EMAIL_1, "invoice", CHUNKS[0]),
        (message_id("e01"), EMAIL_1, "invoice", CHUNKS[1]),
        (message_id("e02"), EMAIL_2, "other", CHUNKS[2]),
    ]

    found = group_stored_rows(rows, ["e01", "e02", "e03"])

    assert set(found) == {"e01", "e02"}
    ids, label = found["e01"]
    assert (ids.email_id, ids.chunk_ids, label) == (EMAIL_1, CHUNKS[:2], "invoice")
    assert found["e02"][0].chunk_ids == [CHUNKS[2]]
