from pathlib import Path
from contextlib import redirect_stdout
from contextlib import redirect_stderr
import io
import json
import tempfile
import unittest

from pdfcheck.cli import main


CORPUS = Path(__file__).resolve().parent / "fixtures" / "ally-2026-09"


class CliTests(unittest.TestCase):
    def test_json_report(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            status = main(["--canvas", "--json", str(target), str(CORPUS / "03_tagged_no_title.pdf")])
            self.assertEqual(0, status)  # Minor findings do not fail CI.
            report = json.loads(target.read_text())
            self.assertEqual(98, report["score"]["score"])
            self.assertEqual("Title:3", report["findings"][0]["ally_code"])

    def test_major_finding_returns_one(self):
        with redirect_stdout(io.StringIO()):
            status = main(["--canvas", "--json", "-", str(CORPUS / "12_figure_without_alt.pdf")])
        self.assertEqual(1, status)

    def test_json_write_failure_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stderr(io.StringIO()):
                status = main(["--canvas", "--json", directory, str(CORPUS / "01_tagged_baseline.pdf")])
        self.assertEqual(2, status)


if __name__ == "__main__":
    unittest.main()
