from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .canvas import run_canvas_checks
from .extract import extract_facts
from .full import run_full_checks
from .model import Report
from .scoring import predict_score


def build_report(path: Path, mode: str) -> Report:
    if mode not in {"canvas", "full"}:
        raise ValueError(f"unsupported mode: {mode}")
    facts = extract_facts(path)
    canvas = run_canvas_checks(facts)
    if mode == "canvas":
        return Report(path, mode, canvas, predict_score(canvas, facts.text_page_count))
    if not facts.parsable or facts.encrypted:
        return Report(path, mode, canvas, None, [], ["Broader checks were not run because the PDF could not be read safely."])
    full, manual, skipped = run_full_checks(facts)
    return Report(path, mode, canvas + full, None, manual, skipped)


def _print_report(report: Report) -> None:
    print(f"{report.path} - {report.mode} accessibility report")
    if report.score:
        score = "unavailable" if report.score.score is None else f"{report.score.score}/100"
        if report.score.lower is not None:
            score += f" (estimated range {report.score.lower}-{report.score.upper})"
        print(f"Predicted Ally score: {score}")
        print(f"Score confidence: {report.score.confidence} - {report.score.basis}")
    if not report.findings:
        print("\nNo automated problems found.")
    else:
        print("\nFindings:")
        order = {"severe": 0, "major": 1, "minor": 2, "review": 3}
        for finding in sorted(report.findings, key=lambda x: order.get(x.severity, 9)):
            code = f" [{finding.ally_code}]" if finding.ally_code else ""
            count = f", {finding.occurrences} occurrences" if finding.occurrences > 1 else ""
            print(f"- {finding.severity.upper()}{code}: {finding.title} ({finding.confidence} confidence{count})")
            print(f"  {finding.message}")
            print(f"  Suggestion: {finding.suggestion}")
    if report.manual_checks:
        print("\nManual review:")
        for item in report.manual_checks:
            print(f"- {item}")
    if report.skipped_checks:
        print("\nEnhanced checks not run:")
        for item in report.skipped_checks:
            print(f"- {item}")


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
