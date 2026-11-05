from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import textwrap

from .canvas import run_canvas_checks
from .extract import extract_facts
from .full import run_full_checks
from .model import Report
from .scoring import predict_score

WIDTH = 88


def build_report(path: Path, mode: str) -> Report:
    if mode not in {"canvas", "full"}:
        raise ValueError(f"unsupported mode: {mode}")
    facts = extract_facts(path)
    canvas = run_canvas_checks(facts)
    if mode == "canvas":
        return Report(path, mode, canvas, predict_score(canvas, facts.text_page_count))
    if not facts.parsable or facts.encrypted:
        return Report(path, mode, canvas, None, [], ["All other checks, because the PDF could not be opened (see the finding above)."])
    full, manual, skipped = run_full_checks(facts)
    return Report(path, mode, canvas + full, None, manual, skipped)


MODE_DESCRIPTIONS = {
    "canvas": "Canvas check: predicts what Anthology Ally will report for this PDF.",
    "full": "Full check: Ally's issues plus broader accessibility checks.",
}
SEVERITY_ORDER = {"severe": 0, "major": 1, "minor": 2, "review": 3}
SEVERITY_LABELS = {"review": "CHECK"}


def _wrap(text: str, **kwargs) -> str:
    # Keep LaTeX snippets and codes such as en-US on one line.
    return textwrap.fill(text, width=WIDTH, break_on_hyphens=False, break_long_words=False, **kwargs)


def _print_report(report: Report) -> None:
    print(report.path)
    print(MODE_DESCRIPTIONS.get(report.mode, f"{report.mode} check"))
    prediction = report.score
    if prediction:
        if prediction.score is None:
            print("\nPredicted Ally score: not available")
        else:
            line = f"\nPredicted Ally score: {prediction.score}%"
            if prediction.lower is not None:
                line += f" (likely between {prediction.lower}% and {prediction.upper}%)"
            print(line)
        print(_wrap(f"Confidence: {prediction.confidence}. {prediction.basis}"))
    if not report.findings:
        print("\nNo problems found by the automated checks.")
    else:
        findings = sorted(report.findings, key=lambda x: SEVERITY_ORDER.get(x.severity, 9))
        noun = "issue" if len(findings) == 1 else "issues"
        print(f"\n{len(findings)} {noun} found, most serious first:")
        for number, finding in enumerate(findings, 1):
            label = SEVERITY_LABELS.get(finding.severity, finding.severity.upper())
            code = f"  [Ally: {finding.ally_code}]" if finding.ally_code else ""
            print(f"\n{number}. {label}: {finding.title}{code}")
            lines = [finding.message, f"Fix: {finding.suggestion}"]
            if prediction and prediction.score is not None and finding.ally_code in prediction.score_if_fixed:
                fixed = prediction.score_if_fixed[finding.ally_code]
                if fixed > prediction.score:
                    lines.append(f"Fixing only this would raise the predicted score to {fixed}%.")
            if finding.confidence != "high":
                note = f" {finding.confidence_note}" if finding.confidence_note else ""
                lines.append(f"Confidence: {finding.confidence}.{note}")
            for text in lines:
                print(_wrap(text, initial_indent="   ", subsequent_indent="   "))
    if report.manual_checks:
        print("\nCheck by hand (automated checks cannot judge these):")
        for item in report.manual_checks:
            print(_wrap(item, initial_indent="- ", subsequent_indent="  "))
    if report.skipped_checks:
        print("\nNot checked:")
        for item in report.skipped_checks:
            print(_wrap(item, initial_indent="- ", subsequent_indent="  "))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdfcheck", description="PDF accessibility checker")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--canvas", action="store_true", help="Predict Anthology Ally findings and score")
    modes.add_argument("--full", action="store_true", help="Run broader accessibility checks and manual-review guidance")
    parser.add_argument("--json", metavar="PATH", help="Write a machine-readable report; use - for stdout")
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args(argv)
    if not args.pdf.is_file():
        parser.error(f"file not found: {args.pdf}")
    report = build_report(args.pdf, "canvas" if args.canvas else "full")
    if args.json:
        payload = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        if args.json == "-":
            print(payload)
        else:
            try:
                Path(args.json).write_text(payload + "\n", encoding="utf-8")
            except OSError as exc:
                print(f"pdfcheck: cannot write JSON report: {exc}", file=sys.stderr)
                return 2
    else:
        _print_report(report)
    return 1 if any(x.severity in {"severe", "major"} for x in report.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
