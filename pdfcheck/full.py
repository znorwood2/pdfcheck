from __future__ import annotations

from .model import DocumentFacts, Finding


def run_full_checks(facts: DocumentFacts) -> tuple[list[Finding], list[str], list[str]]:
    findings: list[Finding] = []
    manual: list[str] = []
    skipped: list[str] = []
    text_chars = sum(len(x.strip()) for x in facts.page_text)
    text_error_pages = [i + 1 for i, failed in enumerate(facts.page_text_errors) if failed]
    image_error_pages = [i + 1 for i, failed in enumerate(facts.page_image_errors) if failed]
    if text_error_pages:
        findings.append(Finding(
            "full.text-extraction-incomplete", "Text extraction was incomplete", "review", "high",
            f"Text extraction failed on pages {text_error_pages}.",
            "Inspect these pages manually; other text-dependent findings may be incomplete.",
            occurrences=len(text_error_pages),
        ))
    if image_error_pages:
        findings.append(Finding(
            "full.image-inspection-incomplete", "Image inspection was incomplete", "review", "high",
            f"Image enumeration failed on pages {image_error_pages}.",
            "Inspect these pages manually; scan and image findings may be incomplete.",
            occurrences=len(image_error_pages),
        ))
    image_only_pages = [
        i + 1
        for i, (text, text_error, images, image_error) in enumerate(zip(
            facts.page_text, facts.page_text_errors, facts.page_image_counts, facts.page_image_errors
        ))
        if not text_error and not image_error and not text.strip() and images
    ]
    if image_only_pages:
        findings.append(Finding(
            "full.probable-scan", "Probable image-only pages", "major", "medium",
            f"Pages {image_only_pages} contain images but no extractable text.",
            "Run OCR, then verify recognition accuracy and reading order.", page=image_only_pages[0],
        ))
    if facts.page_count and text_chars == 0 and not image_only_pages and not text_error_pages:
        findings.append(Finding("full.no-extractable-text", "No extractable text", "major", "high", "No page produced extractable text.", "Check character mappings or provide OCR."))
    # Canvas already reports this at three pages and above. Full mode extends
    # the warning to two-page documents without duplicating the same finding.
    if facts.tagged and facts.page_count == 2 and not facts.headings:
        findings.append(Finding("full.no-headings", "No tagged headings", "major", "high", "The document has multiple pages but no tagged headings.", "Add headings that describe the document organization."))
    if facts.title:
        title = str(facts.title).strip()
        filename = facts.path.stem
        if title.casefold() == filename.casefold() or title.lower().endswith(".pdf") or title.endswith("."):
            findings.append(Finding("full.title-quality", "Document title may not be meaningful", "minor", "high", f"Title is {title!r}.", "Use a human-readable title distinct from the filename."))
    for item in facts.structure:
        if item.resolved_tag == "/Figure" and item.alt:
            alt = str(item.alt).strip()
            if alt.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff")):
                findings.append(Finding("full.alt-filename", "Figure uses a filename as alternative text", "major", "high", f"Alternative text is {alt!r}.", "Describe the figure's purpose or mark it decorative."))
    if facts.page_count >= 10:
        manual.append("Confirm that bookmarks provide useful navigation for this long document.")
    manual.append("Verify that the tag-tree reading order matches the intended visual reading order.")
    if any(x.resolved_tag == "/Figure" for x in facts.structure):
        manual.append("Review whether figure descriptions communicate purpose, not merely appearance.")
    manual.append("Check whether color, position, shape, or sensory language is the only way information is conveyed.")
    if facts.table_header_presence:
        manual.append("Review complex tables with a screen reader, including header associations and spanning cells.")
    if any(facts.page_image_counts):
        manual.append("Inspect contrast and meaningful text inside raster images and diagrams.")
    skipped.extend([
        "Rendered foreground/background contrast analysis (rendering backend not yet selected).",
        "Geometry-assisted reading-order and overlap analysis (rendering backend not yet selected).",
        "Raster effective-resolution analysis (rendering backend not yet selected).",
    ])
    # TODO: add PDF/UA validation adapter, form-field labeling, link purpose,
    # font embedding/ToUnicode checks, table scope validation, and OCR comparison.
    return findings, manual, skipped
