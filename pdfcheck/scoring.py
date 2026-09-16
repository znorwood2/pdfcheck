from __future__ import annotations

from collections import Counter

from .model import Finding, ScorePrediction


SINGLE_ISSUE_SCORES = {
    "Tagged:2": 12,
    "Title:3": 98,
    "LanguagePresence:3": 95,
    "HeadingsPresence:2": 54,
    "HeadingsStartAtOne:3": 95,
    "HeadingsSequential:3": 98,
    "HeadingsHigherLevel:3": 98,
    "AlternativeText:2": 54,
    "TableHeaders:2": 69,
}

CALIBRATED_COMBINATIONS: dict[tuple[tuple[str, int], ...], int] = {
    (): 100,
    (("LanguagePresence:3", 1), ("Tagged:2", 1), ("Title:3", 1)): 6,
    (("Contrast:2", 1), ("LanguagePresence:3", 1), ("Tagged:2", 1), ("Title:3", 1)): 5,
}
CALIBRATED_COMBINATIONS.update({((code, 1),): score for code, score in SINGLE_ISSUE_SCORES.items()})


def predict_score(findings: list[Finding]) -> ScorePrediction:
    counts: Counter[str] = Counter()
    for finding in findings:
        if finding.ally_code:
            counts[finding.ally_code] += max(1, finding.occurrences)
    signature = tuple(sorted(counts.items()))
    if signature in CALIBRATED_COMBINATIONS:
        return ScorePrediction(
            CALIBRATED_COMBINATIONS[signature],
            "medium",
            "Issue combination and occurrence counts match one September 2026 calibration specimen; Ally may also use document composition.",
        )
    known = [SINGLE_ISSUE_SCORES[c] / 100 for c in counts.elements() if c in SINGLE_ISSUE_SCORES]
    unknown = sorted(c for c in counts if c not in SINGLE_ISSUE_SCORES)
    if not known:
        return ScorePrediction(None, "low", "No calibrated score is available for this issue combination.")
    product = 1.0
    for factor in known:
        product *= factor
    estimate = max(0, min(100, round(product * 100)))
    occurrence_count = sum(counts.values())
    spread = 8 + 4 * max(0, occurrence_count - 2) + 5 * len(unknown)
    return ScorePrediction(
        estimate, "low", "Uncalibrated combination; estimate multiplies observed single-issue score ratios.",
        max(0, estimate - spread), min(100, estimate + spread),
    )
