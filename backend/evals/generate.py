"""Generate the synthetic mailbox and its cases.

An LLM plans a scenario and renders each email; cases are derived from the scenario in code,
with only question wording from an LLM.

Run: uv run python -m evals.generate [--out DIR]
     [--reuse-scenario | --cases-only | --add-hard N | --extend-from VERSION]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.config import settings
from evals.cases import (
    RagCase,
    RagIntent,
    label_cases,
    rag_case,
    rag_intents,
    rag_splits,
)
from evals.dataset import data_dir
from evals.emails import build_eml, missing_facts
from evals.llm import GENERATION_MODEL, ask
from evals.questions import phrase_questions
from evals.scenario import (
    EMAILS_PER_LABEL,
    HISTORY_DAYS,
    MIN_TRAPS,
    MIN_UNANSWERABLE,
    OWNER_ADDRESS,
    OWNER_NAME,
    Scenario,
    ScenarioDraft,
    ScenarioEmail,
    ScenarioExtension,
    StoryExtension,
    TrapKind,
    extend,
    extension_problems,
    scenario_problems,
    story_problems,
)
from ingest.email.parse import parse_rfc822

EVALS_ROOT = Path(__file__).resolve().parent
PROMPTS = EVALS_ROOT / "prompts"
DEFAULT_OUT = EVALS_ROOT / "data" / "draft"
SCENARIO_ATTEMPTS = 2
RENDER_ATTEMPTS = 3


class RenderedBody(BaseModel):
    body: str


def generate_scenario(model: str, today: date) -> Scenario:
    system = (
        (PROMPTS / "scenario.md")
        .read_text()
        .format(
            owner_name=OWNER_NAME,
            owner_address=OWNER_ADDRESS,
            today=today.isoformat(),
            labels=_labels(),
            history_days=HISTORY_DAYS,
            per_label=EMAILS_PER_LABEL,
            min_near_duplicate=MIN_TRAPS[TrapKind.NEAR_DUPLICATE],
            min_date_boundary=MIN_TRAPS[TrapKind.DATE_BOUNDARY],
            min_borderline_label=MIN_TRAPS[TrapKind.BORDERLINE_LABEL],
            min_unanswerable=MIN_UNANSWERABLE,
        )
    )
    request = "Write the scenario."
    for attempt in range(1, SCENARIO_ATTEMPTS + 1):
        draft = ask(model, system, request, ScenarioDraft)
        scenario = Scenario(
            **draft.model_dump(),
            today=today,
            owner_name=OWNER_NAME,
            owner_address=OWNER_ADDRESS,
        )
        problems = scenario_problems(scenario)
        if not problems:
            return scenario
        print(f"scenario attempt {attempt}: {len(problems)} problems", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        request = (
            "Write the scenario. A previous attempt had these problems; avoid them:\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )
    raise RuntimeError("no valid scenario; see the problems above")


def extend_scenario(model: str, scenario: Scenario, per_label: int) -> Scenario:
    """Add per_label hard-to-label emails per label. Existing emails are kept as they are."""
    next_key = f"e{len(scenario.emails) + 1:02d}"
    system = (
        (PROMPTS / "hard_emails.md")
        .read_text()
        .format(
            owner_name=scenario.owner_name,
            owner_address=scenario.owner_address,
            today=scenario.today.isoformat(),
            per_label=per_label,
            labels=_labels(),
            next_key=next_key,
            history_days=HISTORY_DAYS,
        )
    )
    existing = scenario.model_dump_json(
        include={"senders", "unanswerable", "emails"}, indent=1
    )
    request = f"The existing mailbox:\n{existing}"
    for attempt in range(1, SCENARIO_ATTEMPTS + 1):
        extension = ask(model, system, request, ScenarioExtension)
        problems = extension_problems(scenario, extension, per_label)
        if not problems:
            return extend(scenario, extension)
        print(f"extension attempt {attempt}: {len(problems)} problems", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        request = (
            f"The existing mailbox:\n{existing}\n\nA previous attempt had these "
            "problems; avoid them:\n" + "\n".join(f"- {p}" for p in problems)
        )
    raise RuntimeError("no valid extension; see the problems above")


def _labels() -> str:
    return (PROMPTS / "labels.md").read_text().strip()


STORY_MINIMUMS = {"multi_email": 5, "superseded": 4, "vague": 5, "unanswerable": 3}


def extend_stories(model: str, scenario: Scenario) -> Scenario:
    """Add story lines, look-alike filler, and planned questions. Existing emails are kept."""
    system = (
        (PROMPTS / "stories.md")
        .read_text()
        .format(
            owner_name=scenario.owner_name,
            owner_address=scenario.owner_address,
            today=scenario.today.isoformat(),
            new_emails=50,
            story_lines=8,
            labels=_labels(),
            min_multi_email=STORY_MINIMUMS["multi_email"],
            min_superseded=STORY_MINIMUMS["superseded"],
            min_vague=STORY_MINIMUMS["vague"],
            min_unanswerable=STORY_MINIMUMS["unanswerable"],
            next_key=f"e{len(scenario.emails) + 1:02d}",
            next_question=f"{len(scenario.questions) + 1:02d}",
            history_days=HISTORY_DAYS,
        )
    )
    existing = scenario.model_dump_json(
        include={"senders", "emails", "unanswerable", "questions"}, indent=1
    )
    request = f"The existing mailbox:\n{existing}"
    for attempt in range(1, SCENARIO_ATTEMPTS + 1):
        extension = ask(model, system, request, StoryExtension)
        problems = story_problems(scenario, extension, STORY_MINIMUMS)
        if not problems:
            return extend(scenario, extension)
        print(f"story attempt {attempt}: {len(problems)} problems", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        request = (
            f"The existing mailbox:\n{existing}\n\nA previous attempt had these "
            "problems; avoid them:\n" + "\n".join(f"- {p}" for p in problems)
        )
    raise RuntimeError("no valid story extension; see the problems above")


def render_email(
    model: str, scenario: Scenario, email: ScenarioEmail
) -> tuple[bytes, int]:
    """Return the .eml bytes and the attempts used. Raise if the facts never all appear."""
    system = (PROMPTS / "render_email.md").read_text()
    sender = next(s for s in scenario.senders if s.key == email.sender_key)
    plan = {
        "from": sender.model_dump(exclude={"key"}),
        "to": scenario.owner_name,
        "sent_at": email.sent_at.isoformat(),
        "subject": email.subject,
        "kind": email.label,
        "brief": email.brief,
        "facts": [fact.model_dump() for fact in email.facts],
        "format": email.body_format,
    }
    request = json.dumps(plan, ensure_ascii=False, indent=2)
    for attempt in range(1, RENDER_ATTEMPTS + 1):
        body = ask(model, system, request, RenderedBody).body
        raw = build_eml(scenario, email, body)
        parsed = parse_rfc822(raw, provider_message_id=email.key, folder="INBOX")
        missing = missing_facts(parsed.body, email.facts)
        if not missing:
            return raw, attempt
        values = ", ".join(repr(fact.value) for fact in missing)
        request = (
            json.dumps(plan, ensure_ascii=False, indent=2)
            + f"\n\nA previous draft left out these fact values: {values}. "
            "Include each one exactly as written."
        )
    raise RuntimeError(
        f"{email.key}: facts still missing after {RENDER_ATTEMPTS} attempts"
    )


def render_all(
    model: str,
    scenario: Scenario,
    out: Path,
    concurrency: int,
    emails: list[ScenarioEmail] | None = None,
) -> dict[str, int | str]:
    """Render emails (default: all) in parallel. Returns attempts per key, or the error text."""
    emails_dir = out / "emails"
    emails_dir.mkdir(parents=True, exist_ok=True)

    def one(email: ScenarioEmail) -> tuple[str, int | str]:
        try:
            raw, attempts = render_email(model, scenario, email)
        except RuntimeError as exc:
            return email.key, str(exc)
        (emails_dir / f"{email.key}.eml").write_bytes(raw)
        return email.key, attempts

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return dict(pool.map(one, scenario.emails if emails is None else emails))


def write_cases(model: str, scenario: Scenario, out: Path) -> None:
    """Rewrite both case files. Existing wording is kept for cases whose intent is unchanged."""
    intents = rag_intents(scenario)
    known = _known_questions(out / "rag_cases.jsonl", intents)
    questions = known | phrase_questions(
        model, scenario, [i for i in intents if i.case_id not in known]
    )
    splits = rag_splits(intents)
    rag = [
        rag_case(intent, questions[intent.case_id], scenario, splits[intent.case_id])
        for intent in intents
    ]
    _write_jsonl(out / "rag_cases.jsonl", rag)
    _write_jsonl(out / "label_cases.jsonl", label_cases(scenario))
    unanswerable = sum(1 for case in rag if not case.answerable)
    print(
        f"cases: {len(rag)} rag ({unanswerable} unanswerable), {len(scenario.emails)} label"
    )


def _known_questions(path: Path, intents: list[RagIntent]) -> dict[str, str]:
    if not path.exists():
        return {}
    existing = {
        case.case_id: case
        for case in map(RagCase.model_validate_json, path.read_text().splitlines())
    }
    return {
        intent.case_id: existing[intent.case_id].question
        for intent in intents
        if intent.case_id in existing
        and existing[intent.case_id].kind == intent.kind
        and existing[intent.case_id].expected_email_keys == intent.expected_email_keys
        and existing[intent.case_id].distractor_keys == intent.distractor_keys
    }


def _write_jsonl(path: Path, rows: Sequence[BaseModel]) -> None:
    path.write_text("".join(row.model_dump_json() + "\n" for row in rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=GENERATION_MODEL)
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=datetime.now(ZoneInfo(settings.email_timezone)).date(),
    )
    parser.add_argument("--concurrency", type=int, default=8)
    step = parser.add_mutually_exclusive_group()
    step.add_argument(
        "--reuse-scenario",
        action="store_true",
        help="Keep the existing scenario.json; re-render emails and rewrite cases.",
    )
    step.add_argument(
        "--cases-only",
        action="store_true",
        help="Keep the existing scenario and emails; only rewrite the case files.",
    )
    step.add_argument(
        "--add-hard",
        type=int,
        metavar="N",
        help=(
            "Keep everything; add N hard-to-label emails per label, render only those, "
            "and rewrite label cases. RAG cases are unaffected."
        ),
    )
    step.add_argument(
        "--extend-from",
        metavar="VERSION",
        help=(
            "Copy a committed data version to --out, then add story lines, look-alike "
            "filler, and planned questions; existing cases keep their wording."
        ),
    )
    args = parser.parse_args()

    scenario_path = args.out / "scenario.json"
    if args.extend_from:
        if args.out.exists():
            print(
                f"{args.out} exists; remove it or pass another --out", file=sys.stderr
            )
            return 1
        shutil.copytree(data_dir(args.extend_from), args.out)
    if args.reuse_scenario or args.cases_only or args.add_hard or args.extend_from:
        scenario = Scenario.model_validate_json(scenario_path.read_text())
    else:
        scenario = generate_scenario(args.model, args.today)
        args.out.mkdir(parents=True, exist_ok=True)
        scenario_path.write_text(scenario.model_dump_json(indent=2) + "\n")

    to_render = [] if args.cases_only else None
    if args.add_hard or args.extend_from:
        known = {email.key for email in scenario.emails}
        if args.add_hard:
            scenario = extend_scenario(args.model, scenario, args.add_hard)
        else:
            scenario = extend_stories(args.model, scenario)
        to_render = [email for email in scenario.emails if email.key not in known]
        scenario_path.write_text(scenario.model_dump_json(indent=2) + "\n")
    print(f"scenario: {len(scenario.emails)} emails, {len(scenario.senders)} senders")

    if to_render != []:
        results = render_all(
            args.model, scenario, args.out, args.concurrency, to_render
        )
        failed = {
            key: result for key, result in results.items() if isinstance(result, str)
        }
        retried = sum(
            1 for result in results.values() if isinstance(result, int) and result > 1
        )
        print(
            f"rendered: {len(results) - len(failed)}, re-rendered: {retried}, failed: {len(failed)}"
        )
        for error in failed.values():
            print(f"  {error}", file=sys.stderr)
        if failed:
            return 1

    write_cases(args.model, scenario, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
