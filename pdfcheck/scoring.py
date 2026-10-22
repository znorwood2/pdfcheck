from __future__ import annotations

from collections import Counter

from .model import Finding, ScorePrediction


# Ally scores of PDFs with exactly one issue, from controlled one-page files
# (three pages for HeadingsPresence, which needs them).
SINGLE_ISSUE_SCORES = {
    "Tagged:2": 12,
    "Title:3": 98,
    "LanguagePresence:3": 95,
    # Inferred: /Lang "fr-FR" on English text and /Lang "english" both scored
    # 95, but the displayed issue codes were not recorded (probes M03, M04).
    "LanguageCorrect:3": 95,
    "HeadingsPresence:2": 54,
    "HeadingsStartAtOne:3": 95,
    "HeadingsSequential:3": 98,
    "HeadingsHigherLevel:3": 98,
    "AlternativeText:2": 54,
    "TableHeaders:2": 69,
    # One-page documents only; see _point_loss.
    "Contrast:2": 5,
}

# Codes whose single-issue score was observed but whose displayed code was not.
INFERRED_CODES = {"LanguageCorrect:3"}

# No non-severe combination has scored below 5, even where the point losses
# add up to far more (AlternativeText + Contrast, TableHeaders + Contrast).
SCORE_FLOOR = 5

# Severe issues observed to drive the score to 0. Scanned:1 is inferred from
# full-page image PDFs that scored 0 (probes S01 and S02).
ZERO_SCORE_CODES = {"Scanned:1"}

# Exact observations. The estimate reproduces every one of these except
# fixture 15 (predicts 5, observed 6), so the table mostly guards regressions.
CALIBRATED_COMBINATIONS: dict[tuple[tuple[str, int], ...], int] = {
    (): 100,
    (("LanguagePresence:3", 1), ("Tagged:2", 1), ("Title:3", 1)): 6,
    (("Contrast:2", 1), ("LanguagePresence:3", 1), ("Tagged:2", 1), ("Title:3", 1)): 5,
    (("LanguagePresence:3", 1), ("Tagged:2", 1)): 7,
    (("Tagged:2", 1), ("Title:3", 1)): 10,
    (("AlternativeText:2", 1), ("LanguagePresence:3", 1), ("Title:3", 1)): 47,
    (("AlternativeText:2", 1), ("Contrast:2", 1)): 5,
    (("Contrast:2", 1), ("TableHeaders:2", 1)): 5,
}
CALIBRATED_COMBINATIONS.update({
    ((code, 1),): score for code, score in SINGLE_ISSUE_SCORES.items() if code not in INFERRED_CODES
})


def _point_loss(code: str, page_count: int | None) -> float:
    loss = 100 - SINGLE_ISSUE_SCORES[code]
    if code == "Contrast:2" and page_count and page_count > 1:
        # Grey text cost 95 points on one-page files (C01-C05, C09), about 48
        # on two pages whether one or both were grey (C07, C08), and fits a
        # third on three pages (C10). Probe batch ally-2026-11 isolates it.
        loss /= page_count
    return loss


def _contrast_is_extrapolated(counts: Counter[str], page_count: int | None) -> bool:
    return "Contrast:2" in counts and page_count != 1


def _is_minor(code: str) -> bool:
    return code.endswith(":3")


def estimate_score(codes: list[str], page_count: int | None = 1) -> int:
    """Estimate a score from observed single-issue scores.

    Major issues (severity 2) multiply: AlternativeText + Contrast and
    HeadingsPresence + three-page Contrast (54 x 0.683 = 37, observed 37)
    fit this; adding them did not. Minor issues (severity 3) then subtract
    their point loss: untagged + no language scored 12 - 5 = 7 and missing
    alt + title + language scored 54 - 2 - 5 = 47, which multiplying did not
    fit. The result never falls below 5.
    """
    score = 100.0
    for code in codes:
        if not _is_minor(code):
            score *= 1 - _point_loss(code, page_count) / 100
    score -= sum(_point_loss(code, page_count) for code in codes if _is_minor(code))
    return max(SCORE_FLOOR, int(score + 0.5))


def predict_score(findings: list[Finding], page_count: int | None = 1) -> ScorePrediction:
    counts: Counter[str] = Counter()
    for finding in findings:
        if finding.ally_code:
            counts[finding.ally_code] += max(1, finding.occurrences)
    zero = sorted(c for c in counts if c in ZERO_SCORE_CODES)
    if zero:
        return ScorePrediction(
            0, "low",
            f"{', '.join(zero)} has been observed to score 0, but the issue itself is predicted with low confidence.",
        )
    signature = tuple(sorted(counts.items()))
    if signature in CALIBRATED_COMBINATIONS and not _contrast_is_extrapolated(counts, page_count):
        return ScorePrediction(
            CALIBRATED_COMBINATIONS[signature],
            "medium",
            "Issue combination and occurrence counts match an observed calibration specimen; Ally may also use document composition.",
        )
    known = [c for c in counts.elements() if c in SINGLE_ISSUE_SCORES]
    unknown = sorted(c for c in counts if c not in SINGLE_ISSUE_SCORES)
    if not known:
        return ScorePrediction(None, "low", "No calibrated score is available for this issue combination.")
    estimate = estimate_score(known, page_count)
    repeated = any(n > 1 for n in counts.values())
    extrapolated = _contrast_is_extrapolated(counts, page_count) or bool(INFERRED_CODES & set(counts))
    majors = sum(1 for c in counts if not _is_minor(c))
    if not unknown and not repeated and not extrapolated and majors <= 1:
        return ScorePrediction(
            estimate, "medium",
            "Unobserved combination of calibrated issues; minor-issue point losses have subtracted exactly in every observed combination.",
        )
    if majors > 1:
        extrapolated = True
    reasons = []
    if repeated:
        reasons.append("repeated issues (whether Ally scales by count is unknown)")
    if extrapolated:
        reasons.append("several major issues, inferred codes, or page-count-dependent contrast (one observation each)")
    if unknown:
        reasons.append(f"uncalibrated issues {unknown}")
    spread = 8 + 4 * max(0, sum(counts.values()) - 2) + 5 * len(unknown)
    return ScorePrediction(
        estimate, "low",
        "Estimate subtracts observed single-issue point losses; includes " + "; ".join(reasons) + ".",
        max(SCORE_FLOOR, estimate - spread), min(100, estimate + spread),
    )
