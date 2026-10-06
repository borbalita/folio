"""Generate the synthetic mailbox: an LLM plans a scenario, then renders each email.

Run: uv run python -m evals.generate [--out DIR] [--reuse-scenario]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings
from evals.emails import build_eml, missing_facts
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
    TrapKind,
    scenario_problems,
)
from ingest.email.parse import parse_rfc822

EVALS_ROOT = Path(__file__).resolve().parent
PROMPTS = EVALS_ROOT / "prompts"
DEFAULT_OUT = EVALS_ROOT / "data" / "draft"
DEFAULT_MODEL = "gpt-6.1-sol"
SCENARIO_ATTEMPTS = 2
RENDER_ATTEMPTS = 3


class RenderedBody(BaseModel):
    body: str


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, timeout=600)


def _ask[T: BaseModel](model: str, system: str, user: str, schema: type[T]) -> T:
    completion = _client().chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=schema,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError(f"{model} returned no parsable {schema.__name__}")
    return parsed


def generate_scenario(model: str, today: date) -> Scenario:
    system = (
        (PROMPTS / "scenario.md")
        .read_text()
        .format(
            owner_name=OWNER_NAME,
            owner_address=OWNER_ADDRESS,
            today=today.isoformat(),
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
        draft = _ask(model, system, request, ScenarioDraft)
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
        body = _ask(model, system, request, RenderedBody).body
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
    model: str, scenario: Scenario, out: Path, concurrency: int
) -> dict[str, int | str]:
    """Render every email in parallel. Returns attempts per key, or the error text."""
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
        return dict(pool.map(one, scenario.emails))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=datetime.now(ZoneInfo(settings.email_timezone)).date(),
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--reuse-scenario",
        action="store_true",
        help="Keep the existing scenario.json and only re-render emails.",
    )
    args = parser.parse_args()

    scenario_path = args.out / "scenario.json"
    if args.reuse_scenario:
        scenario = Scenario.model_validate_json(scenario_path.read_text())
    else:
        scenario = generate_scenario(args.model, args.today)
        args.out.mkdir(parents=True, exist_ok=True)
        scenario_path.write_text(scenario.model_dump_json(indent=2) + "\n")
    print(f"scenario: {len(scenario.emails)} emails, {len(scenario.senders)} senders")

    results = render_all(args.model, scenario, args.out, args.concurrency)
    failed = {key: result for key, result in results.items() if isinstance(result, str)}
    retried = sum(
        1 for result in results.values() if isinstance(result, int) and result > 1
    )
    print(
        f"rendered: {len(results) - len(failed)}, re-rendered: {retried}, failed: {len(failed)}"
    )
    for error in failed.values():
        print(f"  {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
