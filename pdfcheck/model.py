from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StructureElement:
    raw_tag: str
    resolved_tag: str
    alt: str | None = None


@dataclass
class DocumentFacts:
    path: Path
    page_count: int = 0
    encrypted: bool = False
    parsable: bool = True
    parse_error: str | None = None
    title: str | None = None
    language: str | None = None
    tagged: bool = False
    structure: list[StructureElement] = field(default_factory=list)
    page_text: list[str] = field(default_factory=list)
    page_text_errors: list[bool] = field(default_factory=list)
    page_image_counts: list[int] = field(default_factory=list)
    page_image_errors: list[bool] = field(default_factory=list)
    table_header_presence: list[bool] = field(default_factory=list)
    # Lowest WCAG contrast ratio of painted text against an assumed white page.
    lowest_text_contrast: float | None = None
    # Per page: text-showing operators that paint visible glyphs, and the
    # largest fraction of the page covered by a single image.
    page_visible_text_ops: list[int] = field(default_factory=list)
    page_largest_image_coverage: list[float] = field(default_factory=list)

    @property
    def probable_low_contrast_text(self) -> bool:
        return self.lowest_text_contrast is not None and self.lowest_text_contrast < 4.5

    @property
    def headings(self) -> list[StructureElement]:
        return [x for x in self.structure if x.resolved_tag.startswith("/H")]

    @property
    def raw_heading_levels(self) -> list[int]:
        levels: list[int] = []
        for item in self.structure:
            tag = item.raw_tag
            if tag.startswith("/H") and tag[2:].isdigit():
                levels.append(int(tag[2:]))
            elif item.resolved_tag.startswith("/H") and item.resolved_tag[2:].isdigit():
                levels.append(int(item.resolved_tag[2:]))
        return levels


@dataclass(frozen=True)
class Finding:
    check_id: str
    title: str
    severity: str
    confidence: str
    message: str
    suggestion: str
    ally_code: str | None = None
    page: int | None = None
    occurrences: int = 1


@dataclass
class ScorePrediction:
    score: int | None
    confidence: str
    basis: str
    lower: int | None = None
    upper: int | None = None


@dataclass
class Report:
    path: Path
    mode: str
    findings: list[Finding]
    score: ScorePrediction | None = None
    manual_checks: list[str] = field(default_factory=list)
    skipped_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["path"] = str(self.path)
        return value
