from __future__ import annotations

from .language import detect_language, is_valid_language_tag, primary_subtag
from .model import DocumentFacts, Finding

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".svg", ".webp", ".eps", ".pdf")
# Ally scored image PDFs 0 when the image covered 70%, 80% or 100% of the page,
# even with an invisible OCR layer or a visible footer line (probes S01-S05).
# It did not flag fixture 15, whose image covered 58%, but that file also
# differs in image encoding and producer; batch ally-2026-11 separates these.
SCAN_IMAGE_COVERAGE = 0.65
# A page with more visible text than this is not treated as a scan.
SCAN_MAX_VISIBLE_CHARS = 200


def alt_is_filename(alt: str) -> bool:
    return alt.strip().lower().endswith(IMAGE_EXTENSIONS)


def _looks_scanned(facts: DocumentFacts) -> bool:
    pages = list(zip(facts.page_largest_image_coverage, facts.page_visible_text_chars))
    return bool(pages) and all(cover >= SCAN_IMAGE_COVERAGE and text <= SCAN_MAX_VISIBLE_CHARS for cover, text in pages)


def _finding(
    code: str, title: str, severity: str, message: str, suggestion: str,
    confidence: str = "high", occurrences: int = 1,
) -> Finding:
    return Finding(
        check_id=f"canvas.{code.lower()}", ally_code=code, title=title,
        severity=severity, confidence=confidence, message=message, suggestion=suggestion,
        occurrences=occurrences,
    )


def run_canvas_checks(facts: DocumentFacts) -> list[Finding]:
    out: list[Finding] = []
    if not facts.parsable:
        return [_finding("Parsable:1", "PDF is malformed", "severe", facts.parse_error or "The PDF could not be parsed.", "Re-export or repair the PDF.")]
    if facts.encrypted:
        return [_finding("Security:1", "PDF is encrypted", "severe", "The PDF requires a password or restricts access.", "Provide an unencrypted PDF.")]
    if _looks_scanned(facts):
        out.append(_finding(
            "Scanned:1", "PDF appears to be scanned", "severe",
            "Every page is mostly one image with little or no visible text.",
            "Provide the original digital document, or run OCR and then tag the result.", "low",
        ))
    if not facts.tagged:
        out.append(_finding("Tagged:2", "PDF is untagged", "major", "No structure tree is present.", "Export a tagged PDF and verify its reading order."))
    elif not facts.structure:
        # Ally treats an empty tag tree as untagged (probe T02, October 2026).
        out.append(_finding("Tagged:2", "PDF is untagged", "major", "The structure tree contains no elements.", "Export a tagged PDF and verify its reading order."))
    if not facts.title or not str(facts.title).strip():
        out.append(_finding("Title:3", "PDF does not have a title", "minor", "Document title metadata is empty.", "Set a concise, meaningful document title."))
    if not facts.language or not str(facts.language).strip():
        out.append(_finding("LanguagePresence:3", "PDF does not have a language set", "minor", "The document catalog has no language.", "Set the primary document language."))
    elif not is_valid_language_tag(facts.language):
        # Ally deducted 5 points for /Lang "english" (probe M04); which code it
        # displays has not been recorded yet.
        out.append(_finding(
            "LanguageCorrect:3", "PDF language is not a valid code", "minor",
            f"The language {facts.language!r} is not a language code such as 'en-US'.",
            "Set the language with a standard code, for example en-US.", "low",
        ))
    else:
        detected = detect_language(" ".join(facts.page_text))
        if detected and detected != primary_subtag(facts.language):
            out.append(_finding(
                "LanguageCorrect:3", "PDF language may be incorrect", "minor",
                f"The language is set to {facts.language!r}, but the text appears to be {detected!r}.",
                "Set the language that matches the document's main text.", "low",
            ))

    headings = facts.raw_heading_levels
    if facts.tagged and facts.page_count >= 3 and not headings:
        out.append(_finding("HeadingsPresence:2", "PDF does not have headings", "major", "No tagged headings were found in a PDF of at least three pages.", "Add a meaningful heading hierarchy."))
    if headings:
        if headings[0] != 1:
            out.append(_finding("HeadingsStartAtOne:3", "Headings do not begin at level 1", "minor", f"The first heading is H{headings[0]}.", "Begin the hierarchy with an H1."))
        if any(level > 6 for level in headings):
            out.append(_finding("HeadingsHigherLevel:3", "Heading level exceeds H6", "minor", "A heading above level 6 is present.", "Restructure the hierarchy to use H1 through H6."))
        # Ally reports a beyond-H6 heading as HeadingsHigherLevel without also
        # reporting the same transition as HeadingsSequential.
        if any(b <= 6 and b > a + 1 for a, b in zip(headings, headings[1:])):
            out.append(_finding("HeadingsSequential:3", "Headings are not sequential", "minor", f"Heading sequence is {headings}.", "Do not skip heading levels."))

    figures = [x for x in facts.structure if x.resolved_tag == "/Figure"]
    # Ally rejects a filename as alt text (probe F01), which is what LaTeX
    # inserts when no alt text is given.
    missing_alt = sum(x.alt is None or not str(x.alt).strip() for x in figures)
    filename_alt = sum(x.alt is not None and alt_is_filename(str(x.alt)) for x in figures)
    if missing_alt or filename_alt:
        total = missing_alt + filename_alt
        parts = []
        if missing_alt:
            parts.append(f"{missing_alt} with no alternative text")
        if filename_alt:
            parts.append(f"{filename_alt} whose alternative text is a filename")
        noun = "Figure element" if total == 1 else "Figure elements"
        out.append(_finding("AlternativeText:2", "Images lack descriptions", "major", f"{total} {noun}: {', '.join(parts)}.", "Describe the image's purpose, or mark it decorative.", occurrences=total))

    tables_missing_headers = sum(not present for present in facts.table_header_presence)
    if tables_missing_headers:
        noun = "tagged table" if tables_missing_headers == 1 else "tagged tables"
        verb = "has" if tables_missing_headers == 1 else "have"
        out.append(_finding("TableHeaders:2", "Table is missing headers", "major", f"{tables_missing_headers} {noun} {verb} no TH cells.", "Identify row or column headers and set their scope.", occurrences=tables_missing_headers))

    if facts.probable_low_contrast_text:
        ratio = facts.lowest_text_contrast
        # Ally flagged white text (ratio 1.0) in the calibration corpus. Where
        # Ally draws the line between 1.0 and WCAG's 4.5:1 is not yet observed.
        confidence = "medium" if ratio < 1.5 else "low"
        out.append(_finding(
            "Contrast:2", "Text may have insufficient contrast", "major",
            f"Lowest text contrast against a white page is {ratio:.2f}:1 (WCAG AA needs 4.5:1 for body text).",
            "Darken the text, or check it against its actual background if it sits on a dark fill.", confidence,
        ))

    # TODO: Ally's Ocred classifier is not yet reproduced. A full-page image
    # with invisible OCR text still scored 0 (probe S02), like a plain scan.
    return out
