from __future__ import annotations

from .model import DocumentFacts, Finding


def _pages(pages: list[int]) -> str:
    if len(pages) == 1:
        return f"page {pages[0]}"
    return "pages " + ", ".join(map(str, pages[:-1])) + f" and {pages[-1]}"


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
            f"Text could not be extracted from {_pages(text_error_pages)}.",
            "Check these pages by hand; language, contrast and other text-based results may be incomplete.",
            occurrences=len(text_error_pages),
        ))
    if image_error_pages:
        findings.append(Finding(
            "full.image-inspection-incomplete", "Image inspection was incomplete", "review", "high",
            f"Images could not be listed on {_pages(image_error_pages)}.",
            "Check these pages by hand; scan and image results may be incomplete.",
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
            f"{_pages(image_only_pages).capitalize()} {'has' if len(image_only_pages) == 1 else 'have'} images but no text "
            "that can be selected or read aloud, which usually means a scan.",
            "Use the original digital pages, or run OCR and then check the recognised text and reading order.", page=image_only_pages[0],
            confidence_note="A page that is only an image may be intentional, such as a full-page diagram with alt text.",
        ))
    if facts.page_count and text_chars == 0 and not image_only_pages and not text_error_pages:
        findings.append(Finding("full.no-extractable-text", "No extractable text", "major", "high", "No page has text that can be selected or read aloud.", "If the text is visible, its fonts may lack Unicode mappings: re-export with embedded, Unicode-mapped fonts. If the pages are images, run OCR."))
    # Canvas already reports this at three pages and above. Full mode extends
    # the warning to two-page documents without duplicating the same finding.
    if facts.tagged and facts.page_count == 2 and not facts.headings:
        findings.append(Finding("full.no-headings", "No tagged headings", "major", "high", "This 2-page document has no tagged headings. Ally only requires them from three pages, but headings help screen-reader users navigate any multi-page document.", "Use section commands (\\section, \\subsection) for headings rather than bold or large text."))
    if facts.title:
        title = str(facts.title).strip()
        filename = facts.path.stem
        if title.casefold() == filename.casefold() or title.lower().endswith(".pdf") or title.endswith("."):
            findings.append(Finding("full.title-quality", "Document title may not be meaningful", "minor", "high", f"The title is {title!r}, which looks like a filename or sentence rather than a document title.", "Use a short, human-readable title, for example \\hypersetup{pdftitle={Week 3: Cell Biology}}."))
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
        "Contrast of text against its real background; it is currently measured against white (needs a PDF renderer, not yet included).",
        "Reading order and overlapping content compared with the page layout (needs a PDF renderer).",
        "Resolution of embedded images (needs a PDF renderer).",
    ])
    # TODO: add PDF/UA validation adapter, form-field labeling, link purpose,
    # font embedding/ToUnicode checks, table scope validation, and OCR comparison.
    return findings, manual, skipped
