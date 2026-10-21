"""Read back the text strings our demo PDF writer emits (uncompressed `(...) Tj`)."""

from __future__ import annotations

import re

_STRING = re.compile(rb"\(((?:\\.|[^\\)])*)\) Tj")
_ESCAPE = re.compile(rb"\\(.)")


def pdf_strings(pdf: bytes) -> list[str]:
    return [_ESCAPE.sub(rb"\1", raw).decode("cp1252") for raw in _STRING.findall(pdf)]


def pdf_text(pdf: bytes) -> str:
    return "\n".join(pdf_strings(pdf))
