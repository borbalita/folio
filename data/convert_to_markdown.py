# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "docling==2.119.0",
# ]
# ///
"""Convert downloaded SEC HTML filings to Markdown via Docling."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from docling.document_converter import DocumentConverter

DATA_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = DATA_DIR / "downloads"
MARKDOWNS_DIR = DATA_DIR / "markdowns"
MANIFEST_PATH = DOWNLOADS_DIR / "manifest.json"


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    ticker: str
    accession_number: str
    local_path: Path
    markdown_path: Path


def html_path_to_markdown_path(local_path: Path) -> Path:
    """Map downloads/2021/foo.htm → markdowns/2021/foo.md."""
    relative = local_path.relative_to(DOWNLOADS_DIR)
    return MARKDOWNS_DIR / relative.with_suffix(".md")


def load_entries(manifest_path: Path = MANIFEST_PATH) -> list[ManifestEntry]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries: list[ManifestEntry] = []
    for item in payload["filings"]:
        html_path = DOWNLOADS_DIR / item["local_path"]
        entries.append(
            ManifestEntry(
                ticker=item["ticker"],
                accession_number=item["accession_number"],
                local_path=html_path,
                markdown_path=html_path_to_markdown_path(html_path),
            ),
        )
    return entries


def convert_html_to_markdown(html_path: Path, converter: DocumentConverter) -> str:
    result = converter.convert(html_path)
    return result.document.export_to_markdown()


def convert_filing(
    entry: ManifestEntry,
    converter: DocumentConverter,
    *,
    force: bool,
) -> str:
    if entry.markdown_path.is_file() and not force:
        print(f"SKIP {entry.accession_number} → {entry.markdown_path}")
        return "skipped"

    if not entry.local_path.is_file():
        print(f"MISSING {entry.accession_number} → {entry.local_path}")
        return "missing"

    print(f"CONVERT {entry.ticker} {entry.accession_number} …")
    markdown = convert_html_to_markdown(entry.local_path, converter)
    entry.markdown_path.parent.mkdir(parents=True, exist_ok=True)
    entry.markdown_path.write_text(markdown, encoding="utf-8")
    print(f"WROTE {entry.markdown_path} ({len(markdown):,} chars)")
    return "converted"


def run_conversion(
    *,
    limit: int | None = None,
    accession: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    entries = load_entries()
    if accession is not None:
        entries = [entry for entry in entries if entry.accession_number == accession]
    if limit is not None:
        entries = entries[:limit]

    converter = DocumentConverter()
    counts = {"converted": 0, "skipped": 0, "missing": 0}
    for entry in entries:
        result = convert_filing(entry, converter, force=force)
        counts[result] += 1

    print(
        f"Done: converted={counts['converted']} "
        f"skipped={counts['skipped']} missing={counts['missing']}"
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert SEC HTML filings to Markdown")
    parser.add_argument("--limit", type=int, default=None, help="Convert only first N filings")
    parser.add_argument("--accession", type=str, default=None, help="Convert one accession")
    parser.add_argument("--force", action="store_true", help="Overwrite existing markdown files")
    args = parser.parse_args()
    run_conversion(limit=args.limit, accession=args.accession, force=args.force)


if __name__ == "__main__":
    main()
