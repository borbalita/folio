"""Phrase each case's question with an LLM, then check it gives nothing away."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from evals.cases import RagIntent, question_problems
from evals.llm import ask
from evals.scenario import Scenario

PROMPT = Path(__file__).resolve().parent / "prompts" / "questions.md"
PHRASING_ATTEMPTS = 3


class PhrasedQuestion(BaseModel):
    case_id: str
    question: str


class PhrasedQuestions(BaseModel):
    questions: list[PhrasedQuestion]


def phrase_questions(
    model: str, scenario: Scenario, intents: list[RagIntent]
) -> dict[str, str]:
    """Return a question per case ID. Re-ask only for cases whose question was rejected."""
    system = PROMPT.read_text().format(
        owner_name=scenario.owner_name, today=scenario.today.isoformat()
    )
    accepted: dict[str, str] = {}
    if not intents:
        return accepted
    pending = intents
    feedback: dict[str, list[str]] = {}
    for _attempt in range(PHRASING_ATTEMPTS):
        plan = [
            {
                "case_id": intent.case_id,
                "ask": intent.ask,
                "context": intent.context,
                **(
                    {"rejected_because": feedback[intent.case_id]}
                    if intent.case_id in feedback
                    else {}
                ),
            }
            for intent in pending
        ]
        phrased = ask(model, system, json.dumps(plan, indent=2), PhrasedQuestions)
        by_id = {item.case_id: item.question.strip() for item in phrased.questions}
        feedback = {}
        for intent in pending:
            question = by_id.get(intent.case_id)
            problems = (
                ["missing"]
                if not question
                else question_problems(question, intent, scenario)
            )
            if problems:
                feedback[intent.case_id] = problems
            else:
                accepted[intent.case_id] = question
        pending = [intent for intent in pending if intent.case_id in feedback]
        if not pending:
            return accepted
    for case_id, problems in feedback.items():
        print(f"  {case_id}: {'; '.join(problems)}", file=sys.stderr)
    raise RuntimeError(f"{len(feedback)} questions still rejected; see above")
