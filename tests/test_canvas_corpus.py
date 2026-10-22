from pathlib import Path
import unittest

from pdfcheck.canvas import run_canvas_checks
from pdfcheck.extract import extract_facts
from pdfcheck.scoring import predict_score


CORPUS = Path(__file__).resolve().parent / "fixtures" / "ally-2026-09"

EXPECTED = {
    "01_tagged_baseline.pdf": (set(), 100),
    "02_untagged.pdf": ({"Tagged:2"}, 12),
    "03_tagged_no_title.pdf": ({"Title:3"}, 98),
    "04_tagged_no_language.pdf": ({"LanguagePresence:3"}, 95),
    "05_no_headings_2_pages.pdf": (set(), 100),
    "06_no_headings_3_pages.pdf": ({"HeadingsPresence:2"}, 54),
    "07_first_heading_h2.pdf": ({"HeadingsStartAtOne:3"}, 95),
    "08_skipped_heading_level.pdf": ({"HeadingsSequential:3"}, 98),
    "09_sequential_headings.pdf": (set(), 100),
    "10_heading_beyond_h6.pdf": ({"HeadingsHigherLevel:3"}, 98),
    "11_figure_with_alt.pdf": (set(), 100),
    "12_figure_without_alt.pdf": ({"AlternativeText:2"}, 54),
    "13_table_with_headers.pdf": (set(), 100),
    "14_table_without_headers.pdf": ({"TableHeaders:2"}, 69),
    "15_image_only_scan.pdf": ({"Tagged:2", "LanguagePresence:3", "Title:3"}, 6),
    "16_image_with_hidden_text_layer.pdf": ({"Contrast:2", "Tagged:2", "LanguagePresence:3", "Title:3"}, 5),
}


class CanvasCorpusTests(unittest.TestCase):
    def test_observed_ally_results(self):
        for filename, (expected_codes, expected_score) in EXPECTED.items():
            with self.subTest(filename=filename):
                facts = extract_facts(CORPUS / filename)
                findings = run_canvas_checks(facts)
                codes = {x.ally_code for x in findings if x.ally_code}
                self.assertEqual(expected_codes, codes)
                prediction = predict_score(findings, facts.page_count)
                self.assertEqual(expected_score, prediction.score)
                self.assertEqual("medium", prediction.confidence)


if __name__ == "__main__":
    unittest.main()
