import re

import pytest

from app.demo.pdf import Rule, Text, render_pdf
from tests.demo.pdf_text import pdf_strings


def test_pdf_has_header_xref_and_trailer() -> None:
    pdf = render_pdf([Text(56, 800, "Rechnung"), Rule(700)])

    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.endswith(b"%%EOF\n")
    startxref = int(re.search(rb"startxref\n(\d+)\n", pdf).group(1))
    assert pdf[startxref:].startswith(b"xref")
    offsets = re.findall(rb"(\d{10}) 00000 n ", pdf)
    for number, offset in enumerate(offsets, start=1):
        assert pdf[int(offset) :].startswith(f"{number} 0 obj".encode())


def test_text_round_trips_with_umlauts_and_euro() -> None:
    text = "Zahnarztpraxis Dr. Rothenbach, Köln – 1.234,50 €, Hauptstraße"

    assert pdf_strings(render_pdf([Text(56, 800, text)])) == [text]


def test_parentheses_and_backslashes_are_escaped() -> None:
    text = "Strom (Grundversorgung) C:\\x"
    pdf = render_pdf([Text(56, 800, text)])

    assert pdf_strings(pdf) == [text]
    assert b"\\(" in pdf


def test_bold_text_uses_the_bold_font() -> None:
    pdf = render_pdf([Text(56, 800, "RECHNUNG", size=18, bold=True)])

    assert b"/F2 18 Tf" in pdf
    assert b"/Helvetica-Bold" in pdf


def test_rule_draws_a_line() -> None:
    assert b"56 700 m 539 700 l S" in render_pdf([Rule(700)])


def test_text_outside_winansi_is_refused() -> None:
    with pytest.raises(ValueError):
        render_pdf([Text(56, 800, "✓ bezahlt")])
