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


if __name__ == "__main__":
    unittest.main()
