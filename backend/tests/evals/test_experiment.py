from __future__ import annotations

from datetime import date

from evals.experiment import RunConfig, run_metadata, text_hash


def test_run_metadata_records_the_run_and_hashes_prompts() -> None:
    config = RunConfig(
        mode="answer",
        version="v1",
        subject="gpt-6-luna",
        today=date(2026, 10, 6),
        prompts={
            "instructions": "Answer from mail.",
            "rubric_support": "Judge claims.",
        },
    )

    metadata = run_metadata(config, "abc1234-dirty")

    assert metadata == {
        "git_commit": "abc1234-dirty",
        "mode": "answer",
        "subject": "gpt-6-luna",
        "data_version": "v1",
        "today": "2026-10-06",
        "instructions_hash": text_hash("Answer from mail."),
        "rubric_support_hash": text_hash("Judge claims."),
    }
    assert all(isinstance(value, str) for value in metadata.values())


def test_prompt_hash_changes_with_the_text() -> None:
    assert text_hash("a") != text_hash("b")
    assert len(text_hash("a")) == 12
