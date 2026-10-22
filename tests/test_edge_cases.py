from pathlib import Path
import tempfile
import unittest

from pypdf import PdfWriter

from pdfcheck.canvas import run_canvas_checks
from pdfcheck.cli import build_report
from pdfcheck.full import run_full_checks
from pdfcheck.extract import _resolve_role
from pdfcheck.model import DocumentFacts, Finding, StructureElement
from pdfcheck.scoring import predict_score


class EdgeCaseTests(unittest.TestCase):
    def test_chained_role_maps_and_cycles_are_safe(self):
        self.assertEqual("/H1", _resolve_role("/Custom", {"/Custom": "/section", "/section": "/H1"}))
        self.assertIn(_resolve_role("/A", {"/A": "/B", "/B": "/A"}), {"/A", "/B"})

    def test_repeated_issue_is_not_treated_as_single_calibration(self):
        finding = Finding(
            "canvas.alternativetext:2", "Missing alt", "major", "high",
            "Two figures lack alt text.", "Add alt text.", "AlternativeText:2",
            occurrences=2,
        )
        score = predict_score([finding])
        self.assertEqual("low", score.confidence)
        self.assertNotEqual(54, score.score)

    def test_missing_alt_occurrence_count_is_preserved(self):
        facts = DocumentFacts(path=Path("two-figures.pdf"), tagged=True, title="Title", language="en")
        facts.structure = [
            StructureElement("/Figure", "/Figure", None),
            StructureElement("/Figure", "/Figure", ""),
        ]
        finding = next(x for x in run_canvas_checks(facts) if x.ally_code == "AlternativeText:2")
        self.assertEqual(2, finding.occurrences)

    def test_each_table_must_have_a_header(self):
        facts = DocumentFacts(path=Path("tables.pdf"), tagged=True, title="Title", language="en")
        facts.table_header_presence = [True, False]
        finding = next(x for x in run_canvas_checks(facts) if x.ally_code == "TableHeaders:2")
        self.assertEqual(1, finding.occurrences)

    def test_text_extraction_failure_is_not_called_a_scan(self):
        facts = DocumentFacts(
            path=Path("broken-text.pdf"), page_count=1, tagged=True, title="Title", language="en",
            page_text=[""], page_text_errors=[True], page_image_counts=[1], page_image_errors=[False],
        )
        findings, _, _ = run_full_checks(facts)
        ids = {x.check_id for x in findings}
        self.assertNotIn("full.probable-scan", ids)
        self.assertNotIn("full.no-extractable-text", ids)
        self.assertIn("full.text-extraction-incomplete", ids)

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            build_report(Path("unused.pdf"), "other")

    def test_full_report_stops_after_parse_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.pdf"
            path.write_bytes(b"not a pdf")
            with self.assertLogs("pypdf", level="WARNING"):
                report = build_report(path, "full")
        self.assertEqual(["Parsable:1"], [x.ally_code for x in report.findings])
        self.assertEqual([], report.manual_checks)
        self.assertEqual(1, len(report.skipped_checks))

    def test_encrypted_pdf_reports_only_security(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "encrypted.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.encrypt("secret")
            with path.open("wb") as stream:
                writer.write(stream)
            report = build_report(path, "full")
        self.assertEqual(["Security:1"], [x.ally_code for x in report.findings])
        self.assertEqual([], report.manual_checks)

    def test_empty_structure_tree_is_untagged(self):
        facts = DocumentFacts(path=Path("empty.pdf"), tagged=True, title="Title", language="en")
        self.assertIn("Tagged:2", {x.ally_code for x in run_canvas_checks(facts)})

    def test_filename_alt_text_counts_as_missing(self):
        facts = DocumentFacts(path=Path("f.pdf"), tagged=True, title="Title", language="en")
        facts.structure = [StructureElement("/Figure", "/Figure", "IMG_0042.JPG"), StructureElement("/Figure", "/Figure", "A cat")]
        finding = next(x for x in run_canvas_checks(facts) if x.ally_code == "AlternativeText:2")
        self.assertEqual(1, finding.occurrences)

    def test_language_mismatch_and_invalid_code(self):
        english = "The purpose of this handout is to show that the text is in English and that it was written for the class. " * 3
        for lang, expected in [("fr-FR", True), ("english", True), ("en-GB", False), ("EN", False)]:
            facts = DocumentFacts(path=Path("l.pdf"), tagged=True, title="T", language=lang, page_text=[english])
            facts.structure = [StructureElement("/P", "/P")]
            codes = {x.ally_code for x in run_canvas_checks(facts)}
            self.assertEqual(expected, "LanguageCorrect:3" in codes, lang)

    def test_short_text_does_not_trigger_language_guess(self):
        facts = DocumentFacts(path=Path("l.pdf"), tagged=True, title="T", language="de", page_text=["Name: Date:"])
        facts.structure = [StructureElement("/P", "/P")]
        self.assertNotIn("LanguageCorrect:3", {x.ally_code for x in run_canvas_checks(facts)})

    def test_full_page_image_without_visible_text_is_scanned(self):
        def codes(coverage, text_ops):
            facts = DocumentFacts(path=Path("s.pdf"), page_count=1, page_largest_image_coverage=[coverage], page_visible_text_ops=[text_ops])
            return {x.ally_code for x in run_canvas_checks(facts)}
        self.assertIn("Scanned:1", codes(1.0, 0))
        self.assertNotIn("Scanned:1", codes(0.58, 0))  # fixture 15 was not flagged
        self.assertNotIn("Scanned:1", codes(1.0, 5))   # visible text over a background image

    def test_scanned_scores_zero(self):
        finding = Finding("canvas.scanned:1", "Scanned", "severe", "low", "m", "s", "Scanned:1")
        self.assertEqual(0, predict_score([finding]).score)


if __name__ == "__main__":
    unittest.main()
