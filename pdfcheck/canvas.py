from __future__ import annotations

from .language import detect_language, is_valid_language_tag, primary_subtag
from .model import DocumentFacts, Finding

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".svg", ".webp", ".eps", ".pdf")
# Ally scored untagged image PDFs 0 when the image covered 70%, 80% or 100% of
# the page, even with an invisible OCR layer or a visible footer line (probes
# S01-S05). Images covering 58% were not flagged, whether PNG or JPEG (fixture
# 15, probes S06 and S07), so the cut-off lies between 58% and 70%.
SCAN_IMAGE_COVERAGE = 0.65
# A page with more visible text than this is not treated as a scan.
SCAN_MAX_VISIBLE_CHARS = 200
MIN_TABLE_ROWS = 3


def alt_is_filename(alt: str) -> bool:
    return alt.strip().lower().endswith(IMAGE_EXTENSIONS)


def _looks_scanned(facts: DocumentFacts) -> bool:
    # A tagged handout whose figure covered 85% of the page was not flagged
    # (probe S08), so only untagged files are treated as possible scans.
    if facts.tagged and facts.structure:
        return False
    pages = list(zip(facts.page_largest_image_coverage, facts.page_visible_text_chars))
    return bool(pages) and all(cover >= SCAN_IMAGE_COVERAGE and text <= SCAN_MAX_VISIBLE_CHARS for cover, text in pages)


def _finding(
    code: str, title: str, severity: str, message: str, suggestion: str,
    confidence: str = "high", occurrences: int = 1, confidence_note: str | None = None,
) -> Finding:
    return Finding(
        check_id=f"canvas.{code.lower()}", ally_code=code, title=title,
        severity=severity, confidence=confidence, message=message, suggestion=suggestion,
        occurrences=occurrences, confidence_note=confidence_note,
    )


LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese", "nl": "Dutch"}


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _some_figures(n: int, total: int) -> str:
    """Subject and verb, e.g. 'The figure has' or '2 of 5 figures have'."""
    verb = "has" if n == 1 else "have"
    if n == total:
        return f"The figure {verb}" if n == 1 else f"All {n} figures {verb}"
    return f"{n} of {total} figures {verb}"


def run_canvas_checks(facts: DocumentFacts) -> list[Finding]:
    out: list[Finding] = []
    if not facts.parsable:
        detail = f" ({facts.parse_error})" if facts.parse_error else ""
        return [_finding(
            "Parsable:1", "PDF could not be read", "severe",
            f"The file could not be parsed as a PDF{detail}, so no other checks were run.",
            "Re-export the PDF from its source document and check it again.",
        )]
    if facts.encrypted:
        return [_finding(
            "Security:1", "PDF is encrypted", "severe",
            "The PDF is password-protected or restricts access, so Ally (and this tool) cannot check its contents.",
            "Remove the password and permission restrictions, then upload it again.",
        )]
    if _looks_scanned(facts):
        coverage = min(facts.page_largest_image_coverage)
        where = (f"The page is mostly a single image ({coverage:.0%} of its area)"
                 if len(facts.page_largest_image_coverage) == 1
                 else f"Every page is mostly a single image (at least {coverage:.0%} of its area)")
        out.append(_finding(
            "Scanned:1", "PDF appears to be scanned", "severe",
            f"{where} with little visible text. Ally scored PDFs like this 0, even when they had a hidden OCR text layer.",
            "Upload the original digital document instead of a scan. If only a scan exists, run OCR and tag the result.", "low",
            confidence_note=(f"Ally's exact rule is unknown. This tool flags untagged PDFs where every page is at least "
                             f"{SCAN_IMAGE_COVERAGE:.0%} one image; Ally flagged 70% but not 58%."),
        ))
    untagged_fix = ("Export a tagged PDF. In LaTeX, make \\DocumentMetadata{testphase=latest, lang=en-US} "
                    "the first line and compile with LuaLaTeX.")
    if not facts.tagged:
        out.append(_finding(
            "Tagged:2", "PDF is untagged", "major",
            "The PDF has no tags (structure tree), so screen readers get no headings, reading order or alt text. "
            "An untagged PDF scores at most 12 in Ally.", untagged_fix,
        ))
    elif not facts.structure:
        # Ally treats an empty tag tree as untagged (probe T02, October 2026).
        out.append(_finding(
            "Tagged:2", "PDF is untagged", "major",
            "The PDF has a tag tree, but it is empty. Ally treats this as untagged (score at most 12).", untagged_fix,
        ))
    if not facts.title or not str(facts.title).strip():
        out.append(_finding(
            "Title:3", "PDF does not have a title", "minor",
            "The PDF's document information has no Title. Ally reads only this entry; a title stored only in XMP metadata still counts as missing.",
            "Set a meaningful title. In LaTeX: \\hypersetup{pdftitle={Your Title}}.",
        ))
    if not facts.language or not str(facts.language).strip():
        out.append(_finding(
            "LanguagePresence:3", "PDF does not have a language set", "minor",
            "The PDF does not declare its language, so screen readers may pronounce the text wrongly.",
            "Set the main language, for example lang=en-US in \\DocumentMetadata.",
        ))
    elif not is_valid_language_tag(facts.language):
        # Ally deducted 5 points for /Lang "english" (probe M04); which code it
        # displays has not been recorded yet.
        out.append(_finding(
            "LanguageCorrect:3", "PDF language is not a valid code", "minor",
            f"The language is set to {facts.language!r}, which is not a language code such as 'en' or 'en-US'. "
            "Ally deducted 5 points for this in testing.",
            "Use a standard code, for example lang=en-US in \\DocumentMetadata.", "low",
            confidence_note="Ally deducted 5 points in testing, but the wording Ally shows for this issue has not been recorded yet.",
        ))
    else:
        detected = detect_language(" ".join(facts.page_text))
        if detected and detected != primary_subtag(facts.language):
            name = LANGUAGE_NAMES.get(detected, detected)
            out.append(_finding(
                "LanguageCorrect:3", "PDF language may be incorrect", "minor",
                f"The language is set to {facts.language!r}, but the text looks like {name} ({detected}). "
                "Ally deducted 5 points for a mismatched language in testing.",
                f"Set the language that matches the main text, for example lang={detected} in \\DocumentMetadata.", "low",
                confidence_note="The text's language is guessed from common words. Ally deducted 5 points in testing, but the wording Ally shows for this issue has not been recorded yet.",
            ))

    headings = facts.raw_heading_levels
    if facts.tagged and facts.page_count >= 3 and not headings:
        out.append(_finding(
            "HeadingsPresence:2", "PDF does not have headings", "major",
            f"No tagged headings were found in this {facts.page_count}-page PDF. Ally requires headings in PDFs of three or more pages; "
            "bold text on its own line does not count.",
            "Use section commands (\\section, \\subsection) rather than bold or large text for headings.",
        ))
    if headings:
        if headings[0] != 1:
            out.append(_finding(
                "HeadingsStartAtOne:3", "Headings do not begin at level 1", "minor",
                f"The first heading is H{headings[0]}; Ally expects the first heading to be H1.",
                "Make the first heading level 1. In the article class \\section is H1; in report or book, check what \\chapter and \\section produce.",
            ))
        deep = sorted({level for level in headings if level > 6})
        if deep:
            out.append(_finding(
                "HeadingsHigherLevel:3", "Heading level exceeds H6", "minor",
                f"The PDF uses heading level {', '.join(f'H{x}' for x in deep)}; PDF headings only go up to H6.",
                "Restructure the document so headings use H1 through H6 only.",
            ))
        # Ally reports a beyond-H6 heading as HeadingsHigherLevel without also
        # reporting the same transition as HeadingsSequential.
        jumps = [(a, b) for a, b in zip(headings, headings[1:]) if b <= 6 and b > a + 1]
        if jumps:
            shown = ", ".join(f"H{a} to H{b}" for a, b in dict.fromkeys(jumps))
            out.append(_finding(
                "HeadingsSequential:3", "Headings are not sequential", "minor",
                f"Heading levels skip a step: {shown}.",
                "Don't skip levels: an H1 is followed by H2, not H3.",
            ))

    figures = [x for x in facts.structure if x.resolved_tag == "/Figure"]
    # Ally rejects a filename as alt text (probe F01), which is what LaTeX
    # inserts when no alt text is given.
    missing_alt = sum(x.alt is None or not str(x.alt).strip() for x in figures)
    filenames = [str(x.alt).strip() for x in figures if x.alt is not None and alt_is_filename(str(x.alt))]
    if missing_alt or filenames:
        total = missing_alt + len(filenames)
        parts = []
        if missing_alt:
            parts.append(f"{_some_figures(missing_alt, len(figures))} no alternative text")
        if filenames:
            examples = ", ".join(repr(x) for x in filenames[:3]) + (", ..." if len(filenames) > 3 else "")
            parts.append(f"{_some_figures(len(filenames), len(figures))} a filename as alternative text ({examples}), which Ally treats as missing")
        out.append(_finding(
            "AlternativeText:2", "Images lack descriptions", "major",
            "; ".join(parts) + ".",
            "Add alt={...} to each \\includegraphics, describing what the image shows and why it matters. "
            "Without it, LaTeX inserts the filename.",
            occurrences=total,
        ))

    # Ally flagged a three-row table without headers (fixture 14) but not the
    # same table cut to two rows or one row (probes Z01, Z02), a one-cell
    # table (X01) or a two-row table spread over three pages (Y01, Y02).
    rows = facts.table_row_counts or [None] * len(facts.table_header_presence)
    tables_missing_headers = sum(
        not present and (count is None or count >= MIN_TABLE_ROWS)
        for present, count in zip(facts.table_header_presence, rows)
    )
    if tables_missing_headers:
        verb = "has" if tables_missing_headers == 1 else "have"
        out.append(_finding(
            "TableHeaders:2", "Table is missing headers", "major",
            f"{_plural(tables_missing_headers, 'tagged table')} with {MIN_TABLE_ROWS} or more rows {verb} no header cells, "
            "so screen readers cannot announce what each column or row means. (Ally ignores tables of 1-2 rows.)",
            "Mark the header row, for example \\tagpdfsetup{table/header-rows={1}} before the tabular.",
            occurrences=tables_missing_headers,
        ))

    if facts.probable_low_contrast_text:
        ratio = facts.lowest_text_contrast
        # Ally flagged white text (ratio 1.0) in the calibration corpus. Where
        # Ally draws the line between 1.0 and WCAG's 4.5:1 is not yet observed.
        confidence = "medium" if ratio < 1.5 else "low"
        out.append(_finding(
            "Contrast:2", "Text may have insufficient contrast", "major",
            f"The lightest text has a contrast ratio of {ratio:.2f}:1 against a white page; at least 4.5:1 is needed. "
            "In Ally tests the penalty was the same however light the text was, and however many pages had it.",
            "Use a darker colour (#767676 or darker on white). Look for \\color{gray}, black!NN, light link colours, "
            "and white text such as hidden text layers.", confidence,
            confidence_note=("Colours are compared with a white page. Text on a coloured background is not "
                             "judged correctly, and how Ally treats a small amount of grey text is untested."),
        ))

    # TODO: Ally's Ocred classifier is not yet reproduced. A full-page image
    # with invisible OCR text still scored 0 (probe S02), like a plain scan.
    return out
