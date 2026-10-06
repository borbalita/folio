"""Owner review of extraction disagreements, and the reviewed answers it produces (plan 003/04).

`serve` shows a local page (127.0.0.1 only) with every disputed item across all newsletters,
plus every item of the fully checked newsletters, and saves decisions as they are made to the
gitignored evals/out/news-review/<version>/decisions.json. `build` turns runs plus decisions
into the expected items per newsletter and refuses while any decision is missing.

Run: uv run python -m evals.news_review serve|build [--version news-v1]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from evals.dataset import OUT_ROOT
from evals.news_compare import ItemGroup, grounded_choice, group_items, url_in_text
from evals.news_data import DEFAULT_NEWS_VERSION, Newsletter, load_newsletters
from evals.news_runs import RunFile, runs_dir
from ingest.email.news import ExtractedItem

REFERENCE_RUN = "gpt-5.5@default"
FULL_CHECK_PER_SOURCE = 3
PORT = 8765

Verdict = Literal["news", "sponsor", "skip"]


class Decision(BaseModel):
    verdict: Verdict
    run: str | None = None
    """For news and sponsor: whose title and URL are right."""


class MissingItem(BaseModel):
    title: str
    url: str
    sponsor: bool = False


class Decisions(BaseModel):
    runs_hash: str
    """Decisions only fit the run files they were made against."""
    groups: dict[str, Decision] = {}
    missing: dict[str, list[MissingItem]] = {}
    """Newsletter key -> items no run found (full checks only)."""


class ReviewGroup(BaseModel):
    id: str
    reasons: list[str]
    versions: dict[str, ExtractedItem]
    suggested_run: str
    """Preselected version: the one whose URL the text supports, else the reference's."""
    title_key: str
    """Same key across newsletters for recurring blocks, so one decision can cover them all."""
    usable_url: dict[str, bool]
    """Run -> whether its URL is a usable article link; unusable ones become no link."""


class ReviewNewsletter(BaseModel):
    key: str
    source: str
    sent_date: str
    subject: str
    body: str
    full_check: bool
    groups: list[ReviewGroup]


def review_dir(version: str) -> Path:
    return OUT_ROOT / "news-review" / version


def decisions_path(version: str) -> Path:
    return review_dir(version) / "decisions.json"


def load_runs(version: str) -> dict[str, RunFile]:
    runs = {
        path.stem: RunFile.model_validate_json(path.read_text())
        for path in sorted(runs_dir(version).glob("*.json"))
    }
    if REFERENCE_RUN not in runs:
        raise SystemExit(f"missing reference run {REFERENCE_RUN} in {runs_dir(version)}")
    return runs


def runs_hash(version: str) -> str:
    digest = hashlib.sha256()
    for path in sorted(runs_dir(version).glob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def full_check_keys(newsletters: list[Newsletter]) -> set[str]:
    """A fixed, evenly spread pick per source, so the choice can't follow the results."""
    keys: set[str] = set()
    for source in sorted({item.source for item in newsletters}):
        of_source = [item for item in newsletters if item.source == source]
        step = len(of_source) / FULL_CHECK_PER_SOURCE
        keys.update(
            of_source[int(step * index + step / 2)].key
            for index in range(min(FULL_CHECK_PER_SOURCE, len(of_source)))
        )
    return keys


def newsletter_groups(newsletter: Newsletter, runs: dict[str, RunFile]) -> list[ItemGroup]:
    by_run = {
        name: next(r.items for r in run.results if r.key == newsletter.key) or []
        for name, run in runs.items()
    }
    return group_items(by_run, reference=REFERENCE_RUN)


def title_key(title: str) -> str:
    """Lower-case, without digits or punctuation: "TLDR 2026-09-01 Advertise" ~ "TLDR 2026-09-02 Advertise"."""
    letters = "".join(char if char.isalpha() else " " for char in title.casefold())
    return " ".join(letters.split())


def open_reasons(group: ItemGroup, names: list[str], body: str) -> list[str]:
    """Disagreements a person must settle. An item every run flags as a sponsor, with
    nothing else in question, is accepted as a sponsor (approved 2026-10-06); a sponsor
    passed off as news still shows up, as a differing sponsor flag."""
    return [reason for reason in group.disagreement(names, body) if reason != "flagged sponsor"]


def suggested_run(group: ItemGroup, body: str) -> str:
    choice = grounded_choice(group.versions, body)
    if choice is not None:
        return choice
    return REFERENCE_RUN if REFERENCE_RUN in group.versions else next(iter(group.versions))


def build_review(
    newsletters: list[Newsletter], runs: dict[str, RunFile]
) -> list[ReviewNewsletter]:
    full = full_check_keys(newsletters)
    names = list(runs)
    review: list[ReviewNewsletter] = []
    for newsletter in newsletters:
        groups: list[ReviewGroup] = []
        for index, group in enumerate(newsletter_groups(newsletter, runs)):
            reasons = open_reasons(group, names, newsletter.body)
            if reasons or newsletter.key in full:
                groups.append(
                    ReviewGroup(
                        id=f"{newsletter.key}:{index}",
                        reasons=reasons,
                        versions=group.versions,
                        suggested_run=suggested_run(group, newsletter.body),
                        title_key=title_key(next(iter(group.versions.values())).title),
                        usable_url={
                            run: url_in_text(item.url, newsletter.body)
                            for run, item in group.versions.items()
                        },
                    )
                )
        if groups or newsletter.key in full:
            review.append(
                ReviewNewsletter(
                    key=newsletter.key,
                    source=newsletter.source,
                    sent_date=newsletter.sent_date.isoformat(),
                    subject=newsletter.subject,
                    body=newsletter.body,
                    full_check=newsletter.key in full,
                    groups=groups,
                )
            )
    return review


def as_expected(item: ExtractedItem, body: str, sponsor: bool) -> ExtractedItem:
    """The answer key keeps a URL only when it is a usable article link in the text."""
    url = item.url.strip() if url_in_text(item.url, body) else ""
    return item.model_copy(update={"url": url, "sponsor": sponsor})


def expected_items(
    newsletter: Newsletter, runs: dict[str, RunFile], decisions: Decisions, full: bool
) -> tuple[list[ExtractedItem], list[str]]:
    """The reviewed items in reading order, and the group IDs still waiting for a decision."""
    names = list(runs)
    items: list[ExtractedItem] = []
    undecided: list[str] = []
    for index, group in enumerate(newsletter_groups(newsletter, runs)):
        group_id = f"{newsletter.key}:{index}"
        decision = decisions.groups.get(group_id)
        suggested = suggested_run(group, newsletter.body)
        if decision is None:
            if open_reasons(group, names, newsletter.body) or full:
                undecided.append(group_id)
                continue
            # Every run agrees (news, or a sponsor), and the text settles any URL difference.
            agreed = group.versions[suggested]
            items.append(as_expected(agreed, newsletter.body, agreed.sponsor))
            continue
        if decision.verdict == "skip":
            continue
        chosen = group.versions.get(decision.run or suggested) or group.versions[suggested]
        items.append(as_expected(chosen, newsletter.body, decision.verdict == "sponsor"))
    for missing in decisions.missing.get(newsletter.key, []):
        items.append(ExtractedItem(title=missing.title, blurb="", url=missing.url, sponsor=missing.sponsor))
    return items, undecided


def load_decisions(version: str) -> Decisions:
    path = decisions_path(version)
    if not path.exists():
        return Decisions(runs_hash=runs_hash(version))
    return Decisions.model_validate_json(path.read_text())


def _page(review: list[ReviewNewsletter], decisions: Decisions, run_names: list[str]) -> str:
    data = json.dumps(
        {
            "newsletters": [item.model_dump() for item in review],
            "decisions": decisions.model_dump(),
            "runs": run_names,
            "reference": REFERENCE_RUN,
        }
    ).replace("</", "<\\/")
    return (Path(__file__).parent / "news_review.html").read_text().replace("__DATA__", data)


def serve(version: str) -> int:
    newsletters = load_newsletters(version)
    runs = load_runs(version)
    current_hash = runs_hash(version)
    decisions = load_decisions(version)
    if decisions.runs_hash != current_hash:
        print(
            "decisions.json was made against different run files; move it away to start over.",
            file=sys.stderr,
        )
        return 1
    review = build_review(newsletters, runs)
    page = _page(review, decisions, list(runs)).encode()
    path = decisions_path(version)
    path.parent.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            saved = Decisions.model_validate_json(body)
            if saved.runs_hash != current_hash:
                self.send_response(409)
                self.end_headers()
                return
            path.write_text(saved.model_dump_json(indent=2) + "\n")
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    disputed = sum(len(item.groups) for item in review)
    print(f"{len(review)} newsletters, {disputed} items to decide; http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    return 0


def build(version: str) -> int:
    newsletters = load_newsletters(version)
    runs = load_runs(version)
    decisions = load_decisions(version)
    if decisions.runs_hash != runs_hash(version):
        print("decisions.json was made against different run files.", file=sys.stderr)
        return 1
    full = full_check_keys(newsletters)
    reviewed: dict[str, dict[str, object]] = {}
    waiting: list[str] = []
    for newsletter in newsletters:
        items, undecided = expected_items(newsletter, runs, decisions, newsletter.key in full)
        waiting.extend(undecided)
        reviewed[newsletter.key] = {
            "review": "full" if newsletter.key in full else "disputes",
            "items": [item.model_dump() for item in items],
        }
    if waiting:
        print(f"{len(waiting)} items still need a decision, e.g. {waiting[:5]}", file=sys.stderr)
        return 1
    out = review_dir(version) / "expected.json"
    out.write_text(json.dumps(reviewed, indent=2) + "\n")
    total = sum(len(entry["items"]) for entry in reviewed.values())  # type: ignore[arg-type]
    print(f"wrote {total} reviewed items for {len(reviewed)} newsletters to {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve", "build"])
    parser.add_argument("--version", default=DEFAULT_NEWS_VERSION)
    args = parser.parse_args()
    return serve(args.version) if args.command == "serve" else build(args.version)


if __name__ == "__main__":
    sys.exit(main())
