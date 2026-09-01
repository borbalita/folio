"""Load SEC filing manifest entries and resolve markdown paths."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.database.documents import FilingRecord

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
        ticker = item["ticker"]
        records.append(
            FilingRecord(
                ticker=ticker,
                form=item["form"],
                filing_date=date.fromisoformat(item["filing_date"]),
                report_date=date.fromisoformat(item["report_date"]),
                accession_number=item["accession_number"],
                source_url=item["source_url"],
                html_path=html_path,
                markdown_path=markdown_path_from_local_path(item["local_path"]),
                company_name=COMPANY_NAMES.get(ticker, ticker),
            ),
        )

    return records
