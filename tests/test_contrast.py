from pathlib import Path
import tempfile
import unittest

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, NumberObject,
)

from pdfcheck.canvas import run_canvas_checks
from pdfcheck.extract import extract_facts
from pdfcheck.model import DocumentFacts
from pdfcheck.scoring import _additive_estimate, _multiplicative_estimate


def _stream(writer: PdfWriter, data: bytes, extra: dict | None = None):
    stream = DecodedStreamObject()
    stream.set_data(data)
    for key, value in (extra or {}).items():
        stream[NameObject(key)] = value
    return writer._add_object(stream)


def _pdf_with_content(content: bytes, resources: dict | None = None, forms: dict | None = None) -> Path:
    """One-page PDF with a Helvetica font and the given content stream."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    res = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    for key, value in (resources or {}).items():
        res[NameObject(key)] = value
    if forms:
        xobjects = DictionaryObject()
        for name, data in forms.items():
            xobjects[NameObject(name)] = _stream(writer, data, {
                "/Type": NameObject("/XObject"), "/Subtype": NameObject("/Form"),
                "/BBox": ArrayObject([NumberObject(0)] * 2 + [NumberObject(200)] * 2),
                "/Resources": DictionaryObject({NameObject("/Font"): res["/Font"]}),
            })
        res[NameObject("/XObject")] = xobjects
    page[NameObject("/Resources")] = res
    page[NameObject("/Contents")] = _stream(writer, content)
    directory = tempfile.mkdtemp()
    path = Path(directory) / "contrast.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _text(colour_ops: bytes) -> bytes:
    return colour_ops + b"\nBT /F1 12 Tf 20 100 Td (Sample text) Tj ET\n"


class ContrastTests(unittest.TestCase):
    def ratio(self, content: bytes, **kwargs) -> float | None:
        return extract_facts(_pdf_with_content(content, **kwargs)).lowest_text_contrast

    def test_black_text_is_maximum_contrast(self):
        self.assertAlmostEqual(21.0, self.ratio(_text(b"0 g")), places=2)

    def test_wcag_boundary_grey(self):
        # #767676 is the conventional lightest grey passing 4.5:1 on white.
        passing = self.ratio(_text(b"0.4627 0.4627 0.4627 rg"))
        failing = self.ratio(_text(b"0.6 g"))
        self.assertGreaterEqual(passing, 4.5)
        self.assertLess(failing, 4.5)

    def test_light_grey_that_old_heuristic_missed(self):
        # #EEEEEE text was below the previous 0.94 luminance cutoff.
        self.assertLess(self.ratio(_text(b"0.933 g")), 1.5)

    def test_scn_in_device_rgb(self):
        self.assertLess(self.ratio(_text(b"/DeviceRGB cs 0.9 0.9 0.9 scn")), 1.5)

    def test_separation_colour_is_not_guessed(self):
        separation = ArrayObject([NameObject("/Separation"), NameObject("/Spot"), NameObject("/DeviceCMYK"), NameObject("/None")])
        content = _text(b"/CS1 cs 1 scn")  # Full-strength spot ink: dark, not white.
        ratio = self.ratio(content, resources={"/ColorSpace": DictionaryObject({NameObject("/CS1"): separation})})
        self.assertIsNone(ratio)

    def test_invisible_ocr_text_is_ignored(self):
        self.assertIsNone(self.ratio(_text(b"1 g 3 Tr")))

    def test_transparent_black_text_is_light(self):
        gstate = DictionaryObject({NameObject("/GS1"): DictionaryObject({NameObject("/ca"): FloatObject(0.2)})})
        self.assertLess(self.ratio(_text(b"/GS1 gs 0 g"), resources={"/ExtGState": gstate}), 3)

    def test_text_inside_form_xobject(self):
        ratio = self.ratio(b"/Fm1 Do", forms={"/Fm1": _text(b"0.95 g")})
        self.assertLess(ratio, 1.5)

    def test_q_restores_colour(self):
        self.assertAlmostEqual(21.0, self.ratio(b"q 1 g Q " + _text(b"")), places=2)

    def test_mid_grey_reports_low_confidence(self):
        facts = DocumentFacts(path=Path("grey.pdf"), tagged=True, title="T", language="en", lowest_text_contrast=3.0)
        finding = next(x for x in run_canvas_checks(facts) if x.ally_code == "Contrast:2")
        self.assertEqual("low", finding.confidence)


class FallbackScoreTests(unittest.TestCase):
    def test_additive_model_fits_observed_untagged_combination(self):
        # Ally scored Tagged + Title + LanguagePresence at 6 (fixture 15).
        codes = ["Tagged:2", "Title:3", "LanguagePresence:3"]
        self.assertLess(abs(_additive_estimate(codes) - 6), abs(_multiplicative_estimate(codes) - 6))


if __name__ == "__main__":
    unittest.main()
