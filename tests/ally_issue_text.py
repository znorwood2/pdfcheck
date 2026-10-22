"""Turn Ally's instructor-facing issue descriptions into issue codes.

Instructors see sentences such as "This PDF is untagged", not codes such as
Tagged:2, so results.csv accepts either. Separate several issues with ";".
Matching is by keywords because Ally's exact wording can change.
"""
from __future__ import annotations

import re

_CODE = re.compile(r"^[A-Za-z]+:\d$")

# First match wins, so more specific rules come first.
_RULES: list[tuple[tuple[str, ...], str]] = [
    (("scanned",), "Scanned:1"),
    (("ocr",), "Ocred:2"),
    (("encrypt",), "Security:1"),
    (("password",), "Security:1"),
    (("malformed",), "Parsable:1"),
    (("untagged",), "Tagged:2"),
    (("not tagged",), "Tagged:2"),
    (("contrast",), "Contrast:2"),
    (("table", "header"), "TableHeaders:2"),
    (("image",), "AlternativeText:2"),
    (("alternative",), "AlternativeText:2"),
    (("description",), "AlternativeText:2"),
    (("heading", "level 6"), "HeadingsHigherLevel:3"),
    (("heading", "beyond"), "HeadingsHigherLevel:3"),
    (("heading", "h6"), "HeadingsHigherLevel:3"),
    (("heading", "start"), "HeadingsStartAtOne:3"),
    (("heading", "level 1"), "HeadingsStartAtOne:3"),
    (("heading", "sequential"), "HeadingsSequential:3"),
    (("heading", "structure"), "HeadingsSequential:3"),
    (("heading", "skip"), "HeadingsSequential:3"),
    (("heading",), "HeadingsPresence:2"),
    (("title",), "Title:3"),
    (("language", "incorrect"), "LanguageCorrect:3"),
    (("language", "correct"), "LanguageCorrect:3"),
    (("language", "match"), "LanguageCorrect:3"),
    (("language", "wrong"), "LanguageCorrect:3"),
    (("language", "invalid"), "LanguageCorrect:3"),
    (("language",), "LanguagePresence:3"),
]


def issue_codes(cell: str) -> set[str] | None:
    """Codes for a results.csv cell; None when the cell is blank.

    Raises ValueError for a description no rule recognizes.
    """
    cell = cell.strip()
    if not cell:
        return None
    if cell.lower() in {"none", "no issues"}:
        return set()
    cell = re.sub(r"\s+[:|]\s+", ";", cell)
    parts = cell.split(";") if ";" in cell else (cell.replace(",", " ").split() if all(_CODE.match(x) for x in cell.replace(",", " ").split()) else [cell])
    codes = set()
    for part in (p.strip() for p in parts if p.strip()):
        if _CODE.match(part):
            codes.add(part)
            continue
        text = part.lower()
        match = next((code for words, code in _RULES if all(w in text for w in words)), None)
        if match is None:
            raise ValueError(f"unrecognized Ally issue description: {part!r}")
        codes.add(match)
    return codes
