"""Load SEC filing manifest entries and resolve markdown paths."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS_DIR = REPO_ROOT / "data" / "downloads"
MARKDOWNS_DIR = REPO_ROOT / "data" / "markdowns"
DEFAULT_MANIFEST_PATH = DOWNLOADS_DIR / "manifest.json"

COMPANY_NAMES: dict[str, str] = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
}


@dataclass(frozen=True, slots=True)
class FilingRecord:
    ticker: str
    form: str
    filing_date: date
    report_date: date
    accession_number: str
    source_url: str
    html_path: Path
    markdown_path: Path

    @property
    def company_name(self) -> str:
        return COMPANY_NAMES.get(self.ticker, self.ticker)

    @property
    def fiscal_year(self) -> int:
        return self.report_date.year


def html_path_to_markdown_path(html_path: Path) -> Path:
    relative = html_path.relative_to(DOWNLOADS_DIR)
    return MARKDOWNS_DIR / relative.with_suffix(".md")


def markdown_path_from_local_path(local_path: str) -> Path:
    return html_path_to_markdown_path(DOWNLOADS_DIR / local_path)


def load_manifest(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> list[FilingRecord]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[FilingRecord] = []

    for item in payload["filings"]:
        html_path = DOWNLOADS_DIR / item["local_path"]
        records.append(
            FilingRecord(
                ticker=item["ticker"],
                form=item["form"],
                filing_date=date.fromisoformat(item["filing_date"]),
                report_date=date.fromisoformat(item["report_date"]),
                accession_number=item["accession_number"],
                source_url=item["source_url"],
                html_path=html_path,
                markdown_path=markdown_path_from_local_path(item["local_path"]),
            ),
        )

    return records
