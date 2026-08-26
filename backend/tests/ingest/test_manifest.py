from __future__ import annotations

from datetime import date

from ingest.manifest import (
    COMPANY_NAMES,
    DOWNLOADS_DIR,
    MARKDOWNS_DIR,
    FilingRecord,
    markdown_path_from_local_path,
)


def test_markdown_path_from_local_path() -> None:
    path = markdown_path_from_local_path(
        "2021/aapl_10-k_2021-10-29_0000320193-21-000105.htm",
    )
    assert path == (
        MARKDOWNS_DIR / "2021/aapl_10-k_2021-10-29_0000320193-21-000105.md"
    )


def test_filing_record_company_and_fiscal_year() -> None:
    local = "2021/aapl_10-k_2021-10-29_0000320193-21-000105.htm"
    filing = FilingRecord(
        ticker="AAPL",
        form="10-K",
        filing_date=date(2021, 10, 29),
        report_date=date(2021, 9, 25),
        accession_number="0000320193-21-000105",
        source_url="https://example.com",
        html_path=DOWNLOADS_DIR / local,
        markdown_path=markdown_path_from_local_path(local),
    )
    assert filing.company_name == COMPANY_NAMES["AAPL"]
    assert filing.fiscal_year == 2021
