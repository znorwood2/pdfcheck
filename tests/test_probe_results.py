"""Ally observations recorded in probes/*/results.csv are regression tests.

A medium-confidence prediction must equal Ally's score; a low-confidence one
must at least contain it in its range. When the issue-code column is filled
in, the predicted codes must match it too.
"""
import csv
from pathlib import Path
import unittest

from pdfcheck.canvas import run_canvas_checks
from pdfcheck.extract import extract_facts
from pdfcheck.scoring import predict_score

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
                observed = int(row["ally_score"])
                if prediction.confidence == "medium" or prediction.lower is None:
                    self.assertEqual(observed, prediction.score)
                else:
                    self.assertLessEqual(prediction.lower, observed)
                    self.assertGreaterEqual(prediction.upper, observed)
                recorded = row.get("ally_issue_codes", "").replace(",", " ").split()
                if recorded and recorded != ["none"]:
                    self.assertEqual(set(recorded), {x.ally_code for x in findings if x.ally_code})


if __name__ == "__main__":
    unittest.main()
