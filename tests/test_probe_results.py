"""Ally observations recorded in probes/*/results.csv are regression tests.

A medium-confidence prediction must equal Ally's score; a low-confidence one
must at least contain it in its range. Ally's own scores drift by a point
between files with the same issues (S06 scored 5, S07 6), so exact means
within 1. When the issue column is filled in (codes or Ally's descriptions,
see ally_issue_text.py), the predicted codes must match it too.

The optional ally_fix_scores column records the "Increase score up to N%"
figure Ally shows under each issue, as "<issue description> N; ...". Each is
the score with that issue fixed, so it is checked against a prediction made
without that issue.
"""
import csv
from pathlib import Path
import unittest

from pdfcheck.canvas import run_canvas_checks
from pdfcheck.extract import extract_facts
from pdfcheck.scoring import predict_score

try:
    from ally_issue_text import issue_codes
except ImportError:  # run as a package module
    from tests.ally_issue_text import issue_codes

PROBES = Path(__file__).resolve().parents[1] / "probes"


def observations():
    for results in sorted(PROBES.glob("*/results.csv")):
        with results.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("ally_score", "").strip():
                    yield results.parent / row["file"], row


class ProbeResultTests(unittest.TestCase):
    def test_recorded_ally_results(self):
        rows = list(observations())
        self.assertTrue(rows)
        for path, row in rows:
            with self.subTest(file=path.name):
                facts = extract_facts(path)
                findings = run_canvas_checks(facts)
                prediction = predict_score(findings, facts.page_count)
                self.assertScoreFits(int(row["ally_score"]), prediction)
                recorded = issue_codes(row.get("ally_issue_codes", ""))
                if recorded is not None:
                    self.assertEqual(recorded, {x.ally_code for x in findings if x.ally_code})
                for part in filter(str.strip, (row.get("ally_fix_scores") or "").split(";")):
                    description, _, number = part.strip().rpartition(" ")
                    (code,) = issue_codes(description)
                    remaining = [x for x in findings if x.ally_code != code]
                    with self.subTest(fixed=code):
                        self.assertScoreFits(int(number.rstrip("%")), predict_score(remaining, facts.page_count))

    def assertScoreFits(self, observed, prediction):
        if prediction.confidence == "medium" or prediction.lower is None:
            self.assertLessEqual(abs(observed - prediction.score), 1, prediction.basis)
        else:
            self.assertLessEqual(prediction.lower, observed)
            self.assertGreaterEqual(prediction.upper, observed)


class IssueTextTests(unittest.TestCase):
    def test_descriptions_and_codes(self):
        self.assertEqual({"Tagged:2", "Title:3"}, issue_codes("This PDF is untagged; This PDF does not have a title"))
        self.assertEqual({"Tagged:2", "Title:3"}, issue_codes("Tagged:2 Title:3"))
        self.assertEqual({"Scanned:1"}, issue_codes("The PDF is scanned"))
        self.assertEqual({"LanguagePresence:3"}, issue_codes("This PDF does not have a language set"))
        self.assertEqual({"LanguageCorrect:3"}, issue_codes("The language of the PDF is incorrect"))
        self.assertEqual({"HeadingsPresence:2"}, issue_codes("This PDF does not have any headings"))
        self.assertEqual({"HeadingsStartAtOne:3"}, issue_codes("The headings do not start at level 1"))
        self.assertEqual({"AlternativeText:2"}, issue_codes("The image does not have a description"))
        self.assertEqual({"Tagged:2", "Title:3"}, issue_codes("This PDF is untagged : This PDF does not have a title"))
        self.assertEqual(set(), issue_codes("none"))
        self.assertIsNone(issue_codes(""))
        with self.assertRaises(ValueError):
            issue_codes("Something unexpected")


if __name__ == "__main__":
    unittest.main()
