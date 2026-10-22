from __future__ import annotations

from .model import DocumentFacts, Finding


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
    if not facts.tagged:
        out.append(_finding("Tagged:2", "PDF is untagged", "major", "No structure tree is present.", "Export a tagged PDF and verify its reading order."))
    if not facts.title or not str(facts.title).strip():
        out.append(_finding("Title:3", "PDF does not have a title", "minor", "Document title metadata is empty.", "Set a concise, meaningful document title."))
    if not facts.language or not str(facts.language).strip():
        out.append(_finding("LanguagePresence:3", "PDF does not have a language set", "minor", "The document catalog has no language.", "Set the primary document language."))

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
    missing_alt = sum(x.alt is None or not str(x.alt).strip() for x in figures)
    if missing_alt:
        noun = "Figure element" if missing_alt == 1 else "Figure elements"
        verb = "has" if missing_alt == 1 else "have"
        out.append(_finding("AlternativeText:2", "Images lack descriptions", "major", f"{missing_alt} {noun} {verb} no alternative text.", "Add an equivalent description or mark the image decorative.", occurrences=missing_alt))

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

    # TODO: Ally's Scanned/Ocred and LanguageCorrect classifiers are not yet
    # reproducible from the public documentation and current calibration set.
    return out
