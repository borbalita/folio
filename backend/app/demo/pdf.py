"""A one-page A4 PDF of text and horizontal rules, written without a PDF library.

Text uses the standard Helvetica fonts with WinAnsiEncoding (cp1252), which covers
German umlauts, ß, € and the en dash.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

PAGE_WIDTH = 595
PAGE_HEIGHT = 842


@dataclass(frozen=True, slots=True)
class Text:
    x: float
    y: float
    text: str
    size: float = 10
    bold: bool = False


@dataclass(frozen=True, slots=True)
class Rule:
    y: float
    x0: float = 56
    x1: float = 539


def _number(value: float) -> bytes:
    return f"{value:g}".encode()


def _string(text: str) -> bytes:
    try:
        raw = text.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise ValueError(f"Not printable in a WinAnsi PDF: {text!r}") from exc
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _content(items: Sequence[Text | Rule]) -> bytes:
    ops: list[bytes] = []
    for item in items:
        if isinstance(item, Text):
            font = b"/F2" if item.bold else b"/F1"
            ops.append(
                b"BT %s %s Tf %s %s Td (%s) Tj ET"
                % (
                    font,
                    _number(item.size),
                    _number(item.x),
                    _number(item.y),
                    _string(item.text),
                )
            )
        else:
            ops.append(
                b"%s %s m %s %s l S"
                % (_number(item.x0), _number(item.y), _number(item.x1), _number(item.y))
            )
    return b"\n".join(ops)


def _font(name: bytes) -> bytes:
    return (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>"
        % name
    )


def render_pdf(items: Sequence[Text | Rule]) -> bytes:
    content = _content(items)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
        % (PAGE_WIDTH, PAGE_HEIGHT),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        _font(b"Helvetica"),
        _font(b"Helvetica-Bold"),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)
