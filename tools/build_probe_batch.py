"""Build the October 2026 Ally probe batch from the calibrated September corpus.

Each probe copies a fixture Ally has already scored and changes exactly one
property with pypdf, so no LaTeX installation is needed. Upload the output to
Canvas, record Ally's result in results.csv, and the observations can then be
promoted into tests/fixtures with a regression test.

    python tools/build_probe_batch.py
"""
from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path
import re
import sys

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject, TextStringObject, ArrayObject,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pdfcheck.canvas import run_canvas_checks  # noqa: E402
from pdfcheck.extract import extract_facts  # noqa: E402
from pdfcheck.scoring import SINGLE_ISSUE_SCORES, _additive_estimate, _multiplicative_estimate, predict_score  # noqa: E402

CORPUS = ROOT / "tests" / "fixtures" / "ally-2026-09"
OUT = ROOT / "probes" / "ally-2026-10"


def load(name: str) -> PdfWriter:
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(CORPUS / name))
    return writer


def save(writer: PdfWriter, name: str) -> None:
    with (OUT / name).open("wb") as handle:
        writer.write(handle)


def set_content(writer: PdfWriter, page_index: int, data: bytes) -> None:
    stream = DecodedStreamObject()
    stream.set_data(data)
    writer.pages[page_index][NameObject("/Contents")] = writer._add_object(stream)


def recolour_text(writer: PdfWriter, grey: float, pages: list[int] | None = None) -> None:
    """Change LaTeX's black fill resets ("0 g") to a grey, recolouring all body text."""
    for index in pages if pages is not None else range(len(writer.pages)):
        data = writer.pages[index].get_contents().get_data()
        new, count = re.subn(rb"(?<![\d.])0 g\b", f"{grey:.4f} g".encode(), data)
        if not count:
            raise RuntimeError(f"no fill reset found on page {index + 1}")
        set_content(writer, index, new)


def drop_info_title(writer: PdfWriter) -> None:
    if writer._info is not None:
        writer._info.get_object().pop(NameObject("/Title"), None)


def drop_xmp_title(writer: PdfWriter) -> None:
    metadata = writer.root_object.get("/Metadata")
    if metadata is None:
        return
    stream = metadata.get_object()
    stream.set_data(re.sub(rb"\s*<dc:title>.*?</dc:title>", b"", stream.get_data(), flags=re.S))


def set_lang(writer: PdfWriter, value: str | None) -> None:
    if value is None:
        writer.root_object.pop(NameObject("/Lang"), None)
    else:
        writer.root_object[NameObject("/Lang")] = TextStringObject(value)


def struct_elements(writer: PdfWriter):
    root = writer.root_object["/StructTreeRoot"].get_object()
    pending = [root]
    while pending:
        node = pending.pop()
        kids = node.get("/K", [])
        kids = kids if isinstance(kids, list) else [kids]
        for kid in kids:
            try:
                obj = kid.get_object()
            except AttributeError:
                continue
            if hasattr(obj, "get") and "/S" in obj:
                yield obj
                pending.append(obj)


def grey_hex(grey: float) -> str:
    return "#" + f"{round(grey * 255):02X}" * 3


PROBES: list[dict] = []


def probe(name: str, base: str, change: str, question: str, priority: int):
    def register(build):
        PROBES.append({"file": name, "base": base, "change": change, "question": question,
                       "priority": priority, "build": build})
        return build
    return register


# --- Contrast: single-issue score and Ally's threshold --------------------
for index, grey in enumerate([0xEE, 0xCC, 0xAA, 0x95, 0x80, 0x76], start=1):
    level = grey / 255

    def build(level=level):
        writer = load("01_tagged_baseline.pdf")
        recolour_text(writer, level)
        return writer

    probe(f"C{index:02d}_text_{grey_hex(level)[1:]}.pdf", "01_tagged_baseline.pdf",
          f"All text {grey_hex(level)} on white",
          "Is Contrast:2 raised, and what does it cost on its own? (#767676 is the WCAG 4.5:1 pass line)", 1)(build)


@probe("C07_two_pages_one_grey.pdf", "05_no_headings_2_pages.pdf", "Page 2 text #AAAAAA, page 1 black",
       "Does the Contrast penalty scale with how much text is affected? Compare with C08.", 1)
def _():
    writer = load("05_no_headings_2_pages.pdf")
    recolour_text(writer, 0xAA / 255, pages=[1])
    return writer


@probe("C08_two_pages_both_grey.pdf", "05_no_headings_2_pages.pdf", "All text #AAAAAA",
       "Baseline for C07.", 1)
def _():
    writer = load("05_no_headings_2_pages.pdf")
    recolour_text(writer, 0xAA / 255)
    return writer


# --- Score model: do issue penalties add or multiply? ---------------------
@probe("A01_untagged_no_language.pdf", "02_untagged.pdf", "Catalog /Lang removed",
       "Tagged:2 + LanguagePresence:3. Subtracting predicts 7, multiplying predicts 11.", 1)
def _():
    writer = load("02_untagged.pdf")
    set_lang(writer, None)
    return writer


@probe("A02_untagged_no_title.pdf", "02_untagged.pdf", "Info /Title removed",
       "Tagged:2 + Title:3. Subtracting predicts 10, multiplying predicts 12.", 1)
def _():
    writer = load("02_untagged.pdf")
    drop_info_title(writer)
    drop_xmp_title(writer)
    return writer


@probe("A03_no_alt_no_title_no_language.pdf", "12_figure_without_alt.pdf", "Title (Info and XMP) and /Lang removed",
       "AlternativeText:2 + Title:3 + LanguagePresence:3. Subtracting predicts 47, multiplying 50.", 2)
def _():
    writer = load("12_figure_without_alt.pdf")
    drop_info_title(writer)
    drop_xmp_title(writer)
    set_lang(writer, None)
    return writer


@probe("A04_no_alt_grey_text.pdf", "12_figure_without_alt.pdf", "All text #AAAAAA",
       "AlternativeText:2 + Contrast:2: two Major issues together. Interpret with C03.", 1)
def _():
    writer = load("12_figure_without_alt.pdf")
    recolour_text(writer, 0xAA / 255)
    return writer


@probe("A05_table_no_headers_grey_text.pdf", "14_table_without_headers.pdf", "All text #AAAAAA",
       "TableHeaders:2 + Contrast:2. Interpret with C03.", 2)
def _():
    writer = load("14_table_without_headers.pdf")
    recolour_text(writer, 0xAA / 255)
    return writer


# --- Which metadata Ally reads ---------------------------------------------
@probe("M01_title_only_in_xmp.pdf", "01_tagged_baseline.pdf", "Info /Title removed; XMP dc:title kept",
       "Does Ally accept an XMP-only title (normal for PDF 2.0)? pdfcheck currently says no.", 1)
def _():
    writer = load("01_tagged_baseline.pdf")
    drop_info_title(writer)
    return writer


@probe("M02_title_only_in_info.pdf", "01_tagged_baseline.pdf", "XMP dc:title removed; Info /Title kept",
       "Does Ally accept an Info-only title?", 2)
def _():
    writer = load("01_tagged_baseline.pdf")
    drop_xmp_title(writer)
    return writer


@probe("M03_language_says_french.pdf", "05_no_headings_2_pages.pdf", "/Lang fr-FR on English text",
       "Is LanguageCorrect:3 raised, and at what cost? (not implemented in pdfcheck)", 1)
def _():
    writer = load("05_no_headings_2_pages.pdf")
    set_lang(writer, "fr-FR")
    return writer


@probe("M04_language_invalid_code.pdf", "05_no_headings_2_pages.pdf", "/Lang set to 'english' (not a BCP 47 code)",
       "Is a malformed language code treated as present, absent, or incorrect?", 2)
def _():
    writer = load("05_no_headings_2_pages.pdf")
    set_lang(writer, "english")
    return writer


# --- What counts as tagged -------------------------------------------------
@probe("T01_no_markinfo.pdf", "01_tagged_baseline.pdf", "/MarkInfo removed; structure tree kept",
       "Does Ally require /MarkInfo /Marked true to consider a PDF tagged?", 2)
def _():
    writer = load("01_tagged_baseline.pdf")
    writer.root_object.pop(NameObject("/MarkInfo"), None)
    return writer


@probe("T02_empty_structure_tree.pdf", "01_tagged_baseline.pdf", "StructTreeRoot kept but its /K emptied",
       "Is an empty tag tree 'tagged'? Some export tools produce exactly this. pdfcheck currently says tagged.", 1)
def _():
    writer = load("01_tagged_baseline.pdf")
    writer.root_object["/StructTreeRoot"].get_object()[NameObject("/K")] = ArrayObject()
    return writer


# --- Alternative text quality ---------------------------------------------
@probe("F01_alt_is_filename.pdf", "11_figure_with_alt.pdf", "Figure /Alt = 'test-figure.png'",
       "Does Ally accept a filename as alt text? LaTeX inserts one by default.", 1)
def _():
    writer = load("11_figure_with_alt.pdf")
    for element in struct_elements(writer):
        if element.get("/S") == "/Figure":
            element[NameObject("/Alt")] = TextStringObject("test-figure.png")
    return writer


# --- Scans ------------------------------------------------------------------
def scanner_style_pdf(with_ocr: bool) -> PdfWriter:
    image = Image.open(CORPUS / "latex_sources" / "scan-page.png").convert("L")
    buffer = BytesIO()
    image.save(buffer, "PDF", resolution=180)
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(buffer))
    if with_ocr:
        page = writer.pages[0]
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
        resources = page["/Resources"].get_object()
        resources[NameObject("/Font")] = DictionaryObject({NameObject("/OCR"): writer._add_object(font)})
        height = float(page.mediabox.height)
        # Render mode 3 (invisible) is how OCR engines such as Tesseract and
        # OCRmyPDF add their text layer, unlike fixture 16's white text.
        ocr = (f"\nBT 3 Tr /OCR 14 Tf 72 {height - 100:.1f} Td (Scanned handout) Tj "
               "0 -20 Td (This sentence exists only to create the source image.) Tj "
               "0 -40 Td (Name:) Tj 0 -30 Td (Date:) Tj ET\n").encode()
        set_content(writer, 0, page.get_contents().get_data() + ocr)
    return writer


@probe("S01_scanner_style_image.pdf", "15_image_only_scan.pdf", "Same page image saved directly as a PDF (no LaTeX wrapper)",
       "Does a plain image PDF trigger Scanned:1 where the LaTeX-wrapped image (15) did not?", 1)
def _():
    return scanner_style_pdf(with_ocr=False)


@probe("S02_scanner_style_invisible_ocr.pdf", "15_image_only_scan.pdf", "S01 plus an invisible (render mode 3) OCR text layer",
       "Does real-style OCR text trigger Ocred:2, and does it avoid Contrast:2 (16 used white text instead)?", 1)
def _():
    return scanner_style_pdf(with_ocr=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in PROBES:
        save(item["build"](), item["file"])
        findings = run_canvas_checks(extract_facts(OUT / item["file"]))
        codes = sorted(x.ally_code for x in findings if x.ally_code)
        score = predict_score(findings)
        known = [c for c in codes if c in SINGLE_ISSUE_SCORES]
        alt = ""
        if len(known) > 1:
            alt = f"subtract {_additive_estimate(known)} / multiply {_multiplicative_estimate(known)}"
        rows.append({**item, "codes": codes, "score": score.score, "alt": alt})

    with (OUT / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["file", "priority", "pdfcheck_codes", "pdfcheck_score",
                         "ally_score", "ally_issue_codes", "processed_date", "notes"])
        for row in rows:
            writer.writerow([row["file"], row["priority"], " ".join(row["codes"]) or "none",
                             "" if row["score"] is None else row["score"], "", "", "", ""])

    lines = [
        "# Ally probe batch, October 2026",
        "",
        "Generated by `tools/build_probe_batch.py`. Each file is a copy of a September 2026 fixture",
        "that Ally already scored, with exactly one change. Upload them to a Canvas course, wait for",
        "Ally to process them, then fill in `results.csv` with the score and **every** issue shown.",
        "",
        "Priority 1 files answer the questions that most limit pdfcheck's accuracy; priority 2 can wait.",
        "",
        "| File | Pri | Based on | Change | Question | pdfcheck predicts |",
        "|---|---:|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: (r["priority"], r["file"])):
        prediction = ", ".join(row["codes"]) or "no issues"
        if row["score"] is not None:
            prediction += f"; score {row['score']}"
        lines.append(f"| `{row['file']}` | {row['priority']} | `{row['base']}` | {row['change']} | "
                     f"{row['question']} | {prediction} |")
    (OUT / "PROBES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Built {len(rows)} probes in {OUT}")


if __name__ == "__main__":
    main()
