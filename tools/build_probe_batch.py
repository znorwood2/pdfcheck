"""Build Ally probe batches from the calibrated September corpus.

Each probe copies a fixture Ally has already scored and changes exactly one
property with pypdf, so no LaTeX installation is needed. Upload the output to
Canvas, record Ally's result in results.csv, and the observations can then be
promoted into tests/fixtures with a regression test.

    python tools/build_probe_batch.py            # newest batch
    python tools/build_probe_batch.py ally-2026-10

An existing results.csv is never overwritten.
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
from pdfcheck.scoring import predict_score  # noqa: E402

CORPUS = ROOT / "tests" / "fixtures" / "ally-2026-09"
PROBE_ROOT = ROOT / "probes"
BATCH = "ally-2026-10"


def load(name: str) -> PdfWriter:
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(CORPUS / name))
    return writer


def save(writer: PdfWriter, path: Path) -> None:
    with path.open("wb") as handle:
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
                       "priority": priority, "build": build, "batch": BATCH})
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



# ===========================================================================
# Batch 2 (ally-2026-10b): follow-ups to the October 2026 results.
# ===========================================================================
BATCH = "ally-2026-10b"


def keep_first_page(writer: PdfWriter) -> None:
    """Drop page 2+ and prune tag-tree content that pointed at them."""
    first = writer.pages[0].indirect_reference
    while len(writer.pages) > 1:
        writer.remove_page(len(writer.pages) - 1)

    def on_first_page(node, inherited):
        page = node.get("/Pg", inherited) if hasattr(node, "get") else inherited
        return page is None or page.idnum == first.idnum, page

    def prune(node, inherited=None):
        _, page = on_first_page(node, inherited)
        kids = node.get("/K")
        if kids is None:
            return
        listed = kids if isinstance(kids, list) else [kids]
        kept = ArrayObject()
        for kid in listed:
            obj = kid.get_object() if hasattr(kid, "get_object") else kid
            if hasattr(obj, "get"):
                keep, child_page = on_first_page(obj, page)
                if "/S" in obj:
                    prune(obj, child_page)
                    if not keep and not obj.get("/K"):
                        continue
                elif not keep:
                    continue
            elif page is not None and page.idnum != first.idnum:
                continue  # bare MCID on a removed page
            kept.append(kid)
        node[NameObject("/K")] = kept

    prune(writer.root_object["/StructTreeRoot"].get_object())
    writer.root_object["/StructTreeRoot"].get_object().pop(NameObject("/ParentTree"), None)


@probe("C09_one_long_page_grey.pdf", "05_no_headings_2_pages.pdf", "C08 cut to its first page (same text per page), all #AAAAAA",
       "Does the Contrast penalty depend on page count (expect 5) or on the document itself (expect about 50)?", 1)
def _():
    writer = load("05_no_headings_2_pages.pdf")
    keep_first_page(writer)
    recolour_text(writer, 0xAA / 255)
    return writer


@probe("C10_three_pages_grey.pdf", "06_no_headings_3_pages.pdf", "All text #AAAAAA",
       "HeadingsPresence:2 + Contrast:2 on three pages. Dividing the contrast loss by page count predicts 22.", 1)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    recolour_text(writer, 0xAA / 255)
    return writer


def scaled_scan(area: float, visible_line: bool = False) -> PdfWriter:
    writer = scanner_style_pdf(with_ocr=False)
    page = writer.pages[0]
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    k = area ** 0.5
    data = (f"q {w * k:.3f} 0 0 {h * k:.3f} {w * (1 - k) / 2:.3f} {h * (1 - k) / 2:.3f} cm /image Do Q\n").encode()
    if visible_line:
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
        page["/Resources"].get_object()[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): writer._add_object(font)})
        data += b"BT 0 g /F1 9 Tf 36 20 Td (Course handout - page 1) Tj ET\n"
    set_content(writer, 0, data)
    return writer


for _prefix, _area, _pri in [("S03", 0.8, 1), ("S04", 0.7, 2)]:
    probe(f"{_prefix}_scan_{round(_area * 100)}pct_of_page.pdf", "S01_scanner_style_image.pdf",
          f"Page image scaled to cover {round(_area * 100)}% of the page",
          "Where between 58% (fixture 15, not scanned) and 100% (S01, scored 0) does Scanned start?", _pri)(
        lambda area=_area: scaled_scan(area))


@probe("S05_scan_with_visible_footer.pdf", "S01_scanner_style_image.pdf", "Full-page image plus one visible black line of real text",
       "Does a little visible text stop a page counting as scanned? pdfcheck says yes.", 1)
def _():
    return scaled_scan(1.0, visible_line=True)


def set_figure_alt(writer: PdfWriter, alt: str) -> None:
    for element in struct_elements(writer):
        if element.get("/S") == "/Figure":
            element[NameObject("/Alt")] = TextStringObject(alt)


@probe("F02_alt_filename_no_extension.pdf", "11_figure_with_alt.pdf", "Figure /Alt = 'test-figure' (no extension)",
       "Is the filename rule about the extension, or about matching the image name?", 1)
def _():
    writer = load("11_figure_with_alt.pdf")
    set_figure_alt(writer, "test-figure")
    return writer


@probe("F03_alt_generic_word.pdf", "11_figure_with_alt.pdf", "Figure /Alt = 'image'",
       "Does Ally reject generic placeholder alt text?", 2)
def _():
    writer = load("11_figure_with_alt.pdf")
    set_figure_alt(writer, "image")
    return writer


@probe("L01_language_spanish_on_english.pdf", "05_no_headings_2_pages.pdf", "/Lang es-ES on English text",
       "Confirms M03 was a language-mismatch issue rather than something French-specific.", 2)
def _():
    writer = load("05_no_headings_2_pages.pdf")
    set_lang(writer, "es-ES")
    return writer



# ===========================================================================
# Batch 3 (ally-2026-10c): do major issues multiply, how contrast scales with
# pages, and what Ally's scan classifier keys on.
# ===========================================================================
BATCH = "ally-2026-10c"


def struct_with_parents(writer: PdfWriter):
    """Yield (parent, element) for every structure element."""
    pending = [writer.root_object["/StructTreeRoot"].get_object()]
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
                yield node, obj
                pending.append(obj)


def retag(element, tag: str) -> None:
    element[NameObject("/S")] = NameObject(tag)
    element.pop(NameObject("/NS"), None)  # standard PDF 1.7 structure type


def first_paragraph_to_h1(writer: PdfWriter) -> None:
    for _, element in struct_with_parents(writer):
        if element.get("/S") == "/text":
            retag(element, "/H1")
            return
    raise RuntimeError("no paragraph to retag")


def wrap_in_table(writer: PdfWriter, parent_tag: str) -> None:
    """Retag the first /text under parent_tag as a TD inside a new Table > TR."""
    for parent, element in struct_with_parents(writer):
        if parent.get("/S") == parent_tag and element.get("/S") == "/text":
            break
    else:
        raise RuntimeError(f"no /text under {parent_tag}")
    kids = parent["/K"] if isinstance(parent["/K"], list) else ArrayObject([parent["/K"]])
    index = next(i for i, kid in enumerate(kids) if hasattr(kid, "get_object") and kid.get_object() is element)
    element_ref = kids[index]
    table = DictionaryObject({NameObject("/Type"): NameObject("/StructElem"), NameObject("/S"): NameObject("/Table"),
                              NameObject("/P"): element[NameObject("/P")]})
    table_ref = writer._add_object(table)
    row = DictionaryObject({NameObject("/Type"): NameObject("/StructElem"), NameObject("/S"): NameObject("/TR"),
                            NameObject("/P"): table_ref, NameObject("/K"): ArrayObject([element_ref])})
    row_ref = writer._add_object(row)
    table[NameObject("/K")] = ArrayObject([row_ref])
    retag(element, "/TD")
    element[NameObject("/P")] = row_ref
    kids[index] = table_ref
    parent[NameObject("/K")] = kids


@probe("X01_no_alt_and_table_no_headers.pdf", "12_figure_without_alt.pdf", "Caption text re-tagged as a one-cell table without TH",
       "AlternativeText:2 + TableHeaders:2. Multiplying predicts 37; subtracting predicts 23.", 1)
def _():
    writer = load("12_figure_without_alt.pdf")
    wrap_in_table(writer, "/Caption")
    return writer


@probe("X02_three_pages_with_h1.pdf", "06_no_headings_3_pages.pdf", "First visual label re-tagged as H1",
       "Control for X03/X04: should score 100 now that a heading exists.", 1)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    first_paragraph_to_h1(writer)
    return writer


@probe("X03_three_pages_with_h1_grey.pdf", "06_no_headings_3_pages.pdf", "X02 with all text #AAAAAA",
       "Contrast alone on three pages. Dividing by page count predicts 68.", 1)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    first_paragraph_to_h1(writer)
    recolour_text(writer, 0xAA / 255)
    return writer


@probe("X04_three_pages_with_h1_page1_grey.pdf", "06_no_headings_3_pages.pdf", "X02 with only page 1 text #AAAAAA",
       "Does it matter how many pages are grey? Compare with X03.", 2)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    first_paragraph_to_h1(writer)
    recolour_text(writer, 0xAA / 255, pages=[0])
    return writer


@probe("S06_jpeg_scan_at_58pct.pdf", "S01_scanner_style_image.pdf", "S01's JPEG image placed exactly where fixture 15's image is (58% of page)",
       "If this scores 0, image coverage is not why fixture 15 escaped Scanned.", 1)
def _():
    writer = scanner_style_pdf(with_ocr=False)
    set_content(writer, 0, b"q 468.0 0 0 596.18 72 123.826 cm /image Do Q\n")
    return writer


@probe("S07_fixture15_with_jpeg_image.pdf", "15_image_only_scan.pdf", "Image swapped for S01's greyscale JPEG; same size, position and producer",
       "If this scores 0, image encoding (JPEG vs PNG) drives Scanned.", 1)
def _():
    writer = load("15_image_only_scan.pdf")
    source = scanner_style_pdf(with_ocr=False)
    jpeg = source.pages[0]["/Resources"]["/XObject"]["/image"].get_object()
    xobjects = writer.pages[0]["/Resources"]["/XObject"]
    xobjects[NameObject("/Im1")] = writer._add_object(jpeg.clone(writer))
    return writer


@probe("S08_tagged_handout_big_figure.pdf", "11_figure_with_alt.pdf", "Figure (with alt text) enlarged to cover 85% of the page",
       "Does a tagged handout with a large picture count as scanned? pdfcheck currently says yes.", 1)
def _():
    writer = load("11_figure_with_alt.pdf")
    data = writer.pages[0].get_contents().get_data()
    k, x0, y0 = 0.2808, 137.52, 542.985  # the figure's existing transforms
    w, h = 612 * 0.92, 792 * 0.92
    x, y = (612 - w) / 2, (792 - h) / 2
    new = f"{w / k:.3f} 0 0 {h / k:.3f} {(x - x0) / k:.3f} {(y - y0) / k:.3f} cm".encode()
    if data.count(b"1200 0 0 500 0 0 cm") != 1:
        raise RuntimeError("figure transform not found")
    set_content(writer, 0, data.replace(b"1200 0 0 500 0 0 cm", new))
    return writer



# ===========================================================================
# Batch 4 (ally-2026-10d): a real two-by-two table, to test whether major
# issues multiply, and whether Tagged and TableHeaders scale with page count.
# ===========================================================================
BATCH = "ally-2026-10d"


def new_element(writer: PdfWriter, tag: str, parent_ref, kids) -> tuple:
    element = DictionaryObject({NameObject("/Type"): NameObject("/StructElem"), NameObject("/S"): NameObject(tag),
                                NameObject("/P"): parent_ref, NameObject("/K"): ArrayObject(kids)})
    return element, writer._add_object(element)


def document_units(writer: PdfWriter):
    """06's top-level /text-unit elements, in reading order, and their parent."""
    document = writer.root_object["/StructTreeRoot"].get_object()["/K"]
    document = (document[0] if isinstance(document, list) else document).get_object()
    return document, document["/K"]


def heading_first_label(writer: PdfWriter) -> None:
    _, units = document_units(writer)
    text = units[0].get_object()["/K"]
    text = (text[0] if isinstance(text, list) else text).get_object()
    retag(text, "/H1")


def two_by_two_table(writer: PdfWriter, header_row: bool) -> None:
    """Move the /text of units 2-5 into a Table of two rows of two cells."""
    document, units = document_units(writer)
    document_ref = units[0].get_object()["/P"]
    table, table_ref = new_element(writer, "/Table", document_ref, [])
    for row_index, pair in enumerate(([units[1], units[2]], [units[3], units[4]])):
        row, row_ref = new_element(writer, "/TR", table_ref, [])
        for unit in pair:
            text_ref = unit.get_object()["/K"]
            text_ref = text_ref[0] if isinstance(text_ref, list) else text_ref
            text = text_ref.get_object()
            retag(text, "/TH" if header_row and row_index == 0 else "/TD")
            text[NameObject("/P")] = row_ref
            row["/K"].append(text_ref)
        table["/K"].append(row_ref)
    kept = ArrayObject([units[0], table_ref, units[5]])
    document[NameObject("/K")] = kept


@probe("Y01_no_headings_table_no_headers.pdf", "06_no_headings_3_pages.pdf", "Four paragraphs re-tagged as a 2x2 table without TH",
       "HeadingsPresence:2 + TableHeaders:2. Multiplying predicts 37; subtracting predicts 23.", 1)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    two_by_two_table(writer, header_row=False)
    return writer


@probe("Y02_h1_table_no_headers.pdf", "06_no_headings_3_pages.pdf", "Y01 plus an H1, so the table is the only issue",
       "TableHeaders:2 alone on three pages. 69 means no page scaling; about 90 means scaled like Contrast.", 1)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    heading_first_label(writer)
    two_by_two_table(writer, header_row=False)
    return writer


@probe("Y03_h1_table_with_headers.pdf", "06_no_headings_3_pages.pdf", "Y02 with the first row as TH cells",
       "Control: should score 100. Confirms Ally reads the constructed table.", 1)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    heading_first_label(writer)
    two_by_two_table(writer, header_row=True)
    return writer


def untag(writer: PdfWriter) -> None:
    for key in ("/StructTreeRoot", "/MarkInfo"):
        writer.root_object.pop(NameObject(key), None)


@probe("Y04_untagged_three_pages.pdf", "06_no_headings_3_pages.pdf", "Structure tree removed",
       "Tagged:2 alone on three pages. 12 means no page scaling.", 1)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    untag(writer)
    return writer


@probe("Y05_untagged_three_pages_grey.pdf", "06_no_headings_3_pages.pdf", "Structure tree removed, all text #AAAAAA",
       "Tagged:2 + Contrast:2 on three pages. Multiplying predicts 8; subtracting hits the floor of 5.", 2)
def _():
    writer = load("06_no_headings_3_pages.pdf")
    untag(writer)
    recolour_text(writer, 0xAA / 255)
    return writer



# ===========================================================================
# Batch 5 (ally-2026-10e): which tables Ally checks, and what "page count"
# means for the penalties that shrink on longer documents.
# ===========================================================================
BATCH = "ally-2026-10e"


def drop_table_rows(writer: PdfWriter, keep: int) -> None:
    for _, element in struct_with_parents(writer):
        if element.get("/S") == "/Table":
            element[NameObject("/K")] = ArrayObject(list(element["/K"])[:keep])
            return
    raise RuntimeError("no table")


@probe("Z01_table_two_rows.pdf", "14_table_without_headers.pdf", "Third table row removed from the tags (2 rows, one page)",
       "Fixture 14 (3 rows) lost 31 points. Does a 2-row table still count? pdfcheck says no.", 1)
def _():
    writer = load("14_table_without_headers.pdf")
    drop_table_rows(writer, 2)
    return writer


@probe("Z02_table_one_row.pdf", "14_table_without_headers.pdf", "Only the first table row kept in the tags (1 row of 2 cells)",
       "Does a one-row table count?", 2)
def _():
    writer = load("14_table_without_headers.pdf")
    drop_table_rows(writer, 1)
    return writer


def add_blank_pages(writer: PdfWriter, count: int) -> None:
    box = writer.pages[0].mediabox
    for _ in range(count):
        writer.add_blank_page(width=float(box.width), height=float(box.height))


@probe("Z03_grey_plus_two_blank_pages.pdf", "01_tagged_baseline.pdf", "All text #AAAAAA, then two blank pages added",
       "Do blank pages count toward the contrast page scaling? 68 if they do, 5 if only pages with text count.", 1)
def _():
    writer = load("01_tagged_baseline.pdf")
    recolour_text(writer, 0xAA / 255)
    add_blank_pages(writer, 2)
    return writer


@probe("Z04_no_alt_plus_two_blank_pages.pdf", "12_figure_without_alt.pdf", "Two blank pages added",
       "Does the missing-alt penalty (46 on one page) shrink on a three-page file like contrast does?", 1)
def _():
    writer = load("12_figure_without_alt.pdf")
    add_blank_pages(writer, 2)
    return writer


def main(batch: str) -> None:
    probes = [p for p in PROBES if p["batch"] == batch]
    if not probes:
        raise SystemExit(f"unknown batch {batch!r}; choose from {sorted({p['batch'] for p in PROBES})}")
    out = PROBE_ROOT / batch
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "results.csv"
    observed = {}
    if results_path.exists():
        with results_path.open(newline="", encoding="utf-8") as handle:
            observed = {row["file"]: row for row in csv.DictReader(handle)}
    rows = []
    for item in probes:
        path = out / item["file"]
        save(item["build"](), path)
        facts = extract_facts(path)
        findings = run_canvas_checks(facts)
        codes = sorted(x.ally_code for x in findings if x.ally_code)
        rows.append({**item, "codes": codes, "score": predict_score(findings, facts.page_count).score})

    if not results_path.exists():
        with results_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file", "priority", "pdfcheck_codes", "pdfcheck_score",
                             "ally_score", "ally_issue_codes", "ally_fix_scores", "processed_date", "notes"])
            for row in rows:
                writer.writerow([row["file"], row["priority"], " ".join(row["codes"]) or "none",
                                 "" if row["score"] is None else row["score"], "", "", "", "", ""])

    lines = [
        f"# Ally probe batch {batch}",
        "",
        "Generated by `tools/build_probe_batch.py`. Each file is a copy of a fixture",
        "that Ally already scored, with exactly one change. Upload them to a Canvas course, wait for",
        "Ally to process them, then fill in `results.csv` with the score and **every** issue shown.",
        "Paste Ally's issue descriptions separated by `;`, or write `none`. In `ally_fix_scores`,",
        "record the \"Increase score up to N%\" figure under each issue, for example",
        "`This PDF is untagged 93; This PDF does not have a title 7`.",
        "",
        "Priority 1 files answer the questions that most limit pdfcheck's accuracy; priority 2 can wait.",
        "",
        "| File | Pri | Based on | Change | Question | pdfcheck predicts | Ally observed |",
        "|---|---:|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: (r["priority"], r["file"])):
        prediction = ", ".join(row["codes"]) or "no issues"
        if row["score"] is not None:
            prediction += f"; score {row['score']}"
        seen = observed.get(row["file"], {})
        ally = seen.get("ally_score", "").strip()
        if ally and seen.get("ally_issue_codes", "").strip():
            ally += f" ({seen['ally_issue_codes'].strip()})"
        lines.append(f"| `{row['file']}` | {row['priority']} | `{row['base']}` | {row['change']} | "
                     f"{row['question']} | {prediction} | {ally or 'pending'} |")
    (out / "PROBES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Built {len(rows)} probes in {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else PROBES[-1]["batch"])
