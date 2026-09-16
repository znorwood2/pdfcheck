# Contributing

Thank you for helping improve `pdfcheck`.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
```

The test suite uses only the files under `tests/fixtures/`. Do not add screenshots, student information, course identifiers, access tokens, or proprietary documents.

## Design rules

- Keep Ally-compatible issue prediction separate from the broader accessibility audit.
- Do not label a heuristic as certain. Every finding must state a confidence level.
- Do not claim an Ally score is exact unless the scoring behavior has been independently established. Calibration observations belong in tests and documentation.
- Prefer focused, shareable fixtures that vary one property at a time.
- A passing automated check does not prove practical accessibility; preserve manual-review guidance.
- Keep platform-specific programs optional unless there is a compelling, documented reason otherwise.

## Reporting an Ally mismatch

Please include:

1. The smallest PDF you are permitted to share.
2. Ally's displayed score.
3. Every issue displayed for that file.
4. The date and LMS environment in which Ally processed it.
5. `pdfcheck --canvas --json - file.pdf` output.

Redact or replace private course and student information before posting.

## Pull requests

- Add or update tests for behavior changes.
- Run `python -m unittest discover -s tests -v`.
- Explain whether a change affects Canvas prediction, full audit, scoring, or only reporting.
- Document known false positives and false negatives.
