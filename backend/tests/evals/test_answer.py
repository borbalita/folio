from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.database import mailboxes
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer, EmailCitationRef
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailPassage
from app.retrieval.news.retriever import NewsRetriever
from evals.agent_run import OUTPUT_TOOL, run_agent, tool_steps
from evals.cases import ProbeFilters, RagCase
from evals.dataset import IdMap, StoredEmailIds
from evals.replay import ReplayRetriever, evidence_chunk_ids, evidence_email_keys
from evals.scoring import answer_scores, refusal_outcome

USER = UUID("00000000-0000-0000-0000-000000000001")
MAILBOX = UUID("00000000-0000-0000-0000-000000000010")


def _case(expected: list[str], distractors: list[str], case_id: str = "c01") -> RagCase:
    return RagCase(
        case_id=case_id,
        kind="superseded" if expected else "unanswerable",
        question="When is the workshop now?",
        today=date(2026, 10, 1),
        user_id=USER,
        mailbox_id=MAILBOX,
        probe_query="When is the workshop now?",
        probe_filters=ProbeFilters(),
        expected_email_keys=expected,
        expected_facts=[],
        answerable=bool(expected),
        distractor_keys=distractors,
        split="tuning",
    )


def _chunk(n: int) -> UUID:
    return UUID(int=n)


ID_MAP = IdMap(
    version="v2",
    emails={
        "e01": StoredEmailIds(email_id=uuid.uuid4(), chunk_ids=[_chunk(1), _chunk(2)]),
        "e02": StoredEmailIds(email_id=uuid.uuid4(), chunk_ids=[_chunk(3)]),
        "e03": StoredEmailIds(email_id=uuid.uuid4(), chunk_ids=[_chunk(4)]),
    },
)


def _passage(chunk_id: UUID) -> EmailPassage:
    return EmailPassage(
        chunk_id=chunk_id,
        email_id=uuid.uuid4(),
        text="The workshop moved to 28 September.",
        from_address="elin@archive.example",
        subject="Workshop moved",
        sent_at=datetime(2026, 9, 10, tzinfo=UTC),
        mailbox_name="Yahoo",
        fusion_score=0.0,
    )


# Replayed evidence


def test_evidence_is_expected_and_distractor_emails_in_a_fixed_order() -> None:
    case = _case(["e01"], ["e02", "e03"])

    keys = evidence_email_keys(case)

    assert sorted(keys) == ["e01", "e02", "e03"]
    assert evidence_email_keys(case) == keys


def test_evidence_order_differs_between_cases() -> None:
    orders = {
        tuple(evidence_email_keys(_case(["e01"], ["e02", "e03"], f"c{n:02d}")))
        for n in range(1, 20)
    }

    assert len(orders) > 1


def test_evidence_chunks_follow_the_email_order() -> None:
    case = _case(["e01"], ["e02"])

    chunks = evidence_chunk_ids(case, ID_MAP)

    by_email = {"e01": [_chunk(1), _chunk(2)], "e02": [_chunk(3)]}
    assert chunks == [c for key in evidence_email_keys(case) for c in by_email[key]]


def test_unanswerable_case_without_distractors_gets_no_evidence() -> None:
    assert evidence_chunk_ids(_case([], []), ID_MAP) == []


def test_replay_retriever_returns_the_preset_passages_for_any_query() -> None:
    passages = [_passage(_chunk(1))]
    retriever = ReplayRetriever(passages)
    filters = EmailSearchFilters(user_id=USER, mailbox_ids=[MAILBOX])

    first = retriever.search("workshop", filters=filters)
    second = retriever.search("something else", filters=filters)

    assert first == second == passages
    assert retriever.queries_seen == ["workshop", "something else"]


# Scores


@pytest.mark.parametrize(
    ("refused", "answerable", "outcome"),
    [
        (False, True, "correct"),
        (True, False, "correct"),
        (True, True, "wrong_refusal"),
        (False, False, "missing_refusal"),
    ],
)
def test_refusal_outcome(refused: bool, answerable: bool, outcome: str) -> None:
    assert refusal_outcome(refused, answerable) == outcome


def _answer(*chunks: UUID, refused: bool = False) -> EmailAnswer:
    return EmailAnswer(
        answer="It is on 28 September.",
        citations=[
            EmailCitationRef(chunk_id=c, citation_index=i)
            for i, c in enumerate(chunks, start=1)
        ],
        insufficient_evidence=refused,
    )


def test_answer_citing_the_expected_email_scores_full() -> None:
    scores = answer_scores(
        _answer(_chunk(2)),
        answerable=True,
        expected_chunk_ids={_chunk(1), _chunk(2)},
        distractor_chunk_ids={_chunk(3)},
        seen_ids={_chunk(1), _chunk(2), _chunk(3)},
    )

    assert scores.refusal_correct == 1.0
    assert scores.evidence_cited == 1.0
    assert scores.distractor_cited == 0.0
    assert (scores.grounding_pass, scores.grounding_error) == (1.0, None)


def test_citing_only_the_outdated_email_misses_evidence() -> None:
    scores = answer_scores(
        _answer(_chunk(3)),
        answerable=True,
        expected_chunk_ids={_chunk(1)},
        distractor_chunk_ids={_chunk(3)},
        seen_ids={_chunk(1), _chunk(3)},
    )

    assert scores.evidence_cited == 0.0
    assert scores.distractor_cited == 1.0


def test_wrong_refusal_misses_evidence_and_has_no_distractor_score() -> None:
    scores = answer_scores(
        _answer(refused=True),
        answerable=True,
        expected_chunk_ids={_chunk(1)},
        distractor_chunk_ids={_chunk(3)},
        seen_ids={_chunk(1), _chunk(3)},
    )

    assert scores.refusal_outcome == "wrong_refusal"
    assert scores.evidence_cited == 0.0
    assert scores.distractor_cited is None
    assert scores.grounding_pass == 1.0


def test_citing_an_unseen_chunk_fails_grounding() -> None:
    scores = answer_scores(
        _answer(_chunk(9)),
        answerable=True,
        expected_chunk_ids={_chunk(1)},
        distractor_chunk_ids=set(),
        seen_ids={_chunk(1)},
    )

    assert (scores.grounding_pass, scores.grounding_error) == (0.0, "unknown_chunk")


def test_unanswerable_case_without_evidence_is_scored_on_refusal_only() -> None:
    scores = answer_scores(
        _answer(refused=True),
        answerable=False,
        expected_chunk_ids=set(),
        distractor_chunk_ids=set(),
        seen_ids=set(),
    )

    assert scores.refusal_correct == 1.0
    assert (scores.evidence_cited, scores.distractor_cited) == (None, None)
    assert scores.grounding_pass is None


def test_answering_an_unanswerable_case_from_a_look_alike() -> None:
    scores = answer_scores(
        _answer(_chunk(3)),
        answerable=False,
        expected_chunk_ids=set(),
        distractor_chunk_ids={_chunk(3)},
        seen_ids={_chunk(3)},
    )

    assert scores.refusal_outcome == "missing_refusal"
    assert scores.distractor_cited == 1.0
    assert scores.grounding_pass == 1.0


# Step record and agent run


def test_tool_steps_pair_calls_with_results_and_skip_the_answer_tool() -> None:
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="When?")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="search_emails", args={"query": "a"}, tool_call_id="1"
                ),
                ToolCallPart(
                    tool_name="search_emails", args='{"query": "b"}', tool_call_id="2"
                ),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="search_emails", content="first", tool_call_id="1"
                ),
                ToolReturnPart(
                    tool_name="search_emails", content="second", tool_call_id="2"
                ),
            ]
        ),
        ModelResponse(
            parts=[
                TextPart(content="thinking aloud"),
                ToolCallPart(tool_name=OUTPUT_TOOL, args={}, tool_call_id="3"),
            ]
        ),
    ]

    steps = tool_steps(messages)

    assert [(s.tool, s.args, s.result) for s in steps] == [
        ("search_emails", {"query": "a"}, "first"),
        ("search_emails", '{"query": "b"}', "second"),
    ]


def test_agent_run_searches_the_replay_and_records_its_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda _user: [MAILBOX])
    passage = _passage(_chunk(1))
    prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returned = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if not returned:
            prompts.extend(
                part.content
                for part in messages[0].parts
                if isinstance(part, UserPromptPart)
            )
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="search_emails",
                        args={"query": "workshop date"},
                        tool_call_id="s1",
                    )
                ]
            )
        output = info.output_tools[0].name
        answer = {
            "answer": "28 September.",
            "citations": [{"chunk_id": str(_chunk(1)), "citation_index": 1}],
        }
        return ModelResponse(
            parts=[ToolCallPart(tool_name=output, args=answer, tool_call_id="o1")]
        )

    deps = EmailAgentDeps(
        user_id=USER,
        thread_id=uuid.uuid4(),
        retriever=ReplayRetriever([passage]),
        news=NewsRetriever(),
    )

    record = asyncio.run(
        run_agent(
            "When is the workshop now?",
            date(2026, 10, 1),
            deps,
            FunctionModel(respond),
        )
    )

    assert prompts and prompts[0].startswith("Today is 2026-10-01")
    assert [s.tool for s in record.steps] == ["search_emails"]
    assert record.steps[0].args == {"query": "workshop date"}
    assert str(_chunk(1)) in (record.steps[0].result or "")
    assert record.answer.citations[0].chunk_id == _chunk(1)
    assert deps.seen_ids == {_chunk(1)}
    assert record.usage["requests"] == 2
