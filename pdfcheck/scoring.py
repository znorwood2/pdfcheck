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


# Codes Ally charges once however many times they occur. An 18-page PDF with
# 11 headerless tables (and four red labels) scored 69, the one-table score,
# and Ally said fixing the tables would raise it to 100 (November 2026).
CHARGED_ONCE = {"TableHeaders:2"}


def _contrast_weight(scale: float | None) -> float:
    """canvas.contrast_scale: below 1 when only a little text fails."""
    return 1.0 if scale is None else min(1.0, max(0.0, scale))


def _point_loss(code: str, page_count: int | None, contrast_scale: float | None = None) -> float:
    loss = 100 - SINGLE_ISSUE_SCORES[code]
    if code == "Contrast:2":
        if page_count and page_count > 1:
            # Grey text cost 95 points on one-page files (C01-C05, C09), about
            # 48 on two pages (C07, C08) and 32-33 on three (X03, X04), however
            # many of the pages were grey. Blank pages do not count (Z03), so
            # callers pass the number of pages with visible text.
            loss /= page_count
        loss *= _contrast_weight(contrast_scale)
    return loss


def _contrast_is_extrapolated(counts: Counter[str], page_count: int | None, contrast_scale: float | None = None) -> bool:
    return "Contrast:2" in counts and (page_count != 1 or _contrast_weight(contrast_scale) < 1)


def _is_minor(code: str) -> bool:
    return code.endswith(":3")


def estimate_score(codes: list[str], page_count: int | None = 1, contrast_scale: float | None = None) -> int:
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
            score *= 1 - _point_loss(code, page_count, contrast_scale) / 100
    score -= sum(_point_loss(code, page_count) for code in codes if _is_minor(code))
    return max(SCORE_FLOOR, int(score + 0.5))


# Plain-language names for score explanations.
ISSUE_NAMES = {
    "Parsable:1": "unreadable PDF",
    "Security:1": "encryption",
    "Scanned:1": "scanned pages",
    "Tagged:2": "missing tags",
    "Title:3": "missing title",
    "LanguagePresence:3": "missing language",
    "LanguageCorrect:3": "wrong or invalid language",
    "HeadingsPresence:2": "missing headings",
    "HeadingsStartAtOne:3": "first heading not H1",
    "HeadingsSequential:3": "skipped heading level",
    "HeadingsHigherLevel:3": "heading beyond H6",
    "AlternativeText:2": "images without alt text",
    "TableHeaders:2": "tables without headers",
    "Contrast:2": "low-contrast text",
}


def _name(code: str) -> str:
    return ISSUE_NAMES.get(code, code)


def _names(codes) -> str:
    return ", ".join(_name(c) for c in codes)


def _predict(counts: Counter[str], page_count: int | None, contrast_scale: float | None = None) -> ScorePrediction:
    zero = sorted(c for c in counts if c in ZERO_SCORE_CODES)
    if zero:
        return ScorePrediction(
            0, "low",
            f"Ally scored every test PDF with {_names(zero)} 0, but this tool detects that issue "
            "with a rule of thumb, not Ally's own method.",
        )
    signature = tuple(sorted(counts.items()))
    if signature in CALIBRATED_COMBINATIONS and not _contrast_is_extrapolated(counts, page_count, contrast_scale):
        if not signature:
            basis = ("None of the issues this tool checks for were found, and Ally scored such test "
                     "PDFs 100. Ally may still report problems this tool does not check.")
        else:
            basis = (f"In testing, Ally gave this score to a PDF with exactly these issues ({_names(counts)}). "
                     "The test PDFs were 1-3 pages long, so longer documents may score differently.")
        return ScorePrediction(CALIBRATED_COMBINATIONS[signature], "medium", basis)
    known = [c for c in counts.elements() if c in SINGLE_ISSUE_SCORES]
    unknown = sorted(c for c in counts if c not in SINGLE_ISSUE_SCORES)
    if not known:
        return ScorePrediction(None, "low", f"Ally has not yet scored a PDF with {_names(unknown)}, so no estimate is possible.")
    estimate = estimate_score(known, page_count, contrast_scale)
    repeated = sorted(c for c, n in counts.items() if n > 1)
    contrast = _contrast_is_extrapolated(counts, page_count, contrast_scale)
    little_text = "Contrast:2" in counts and _contrast_weight(contrast_scale) < 1
    inferred = sorted(INFERRED_CODES & set(counts))
    majors = sorted(c for c in counts if not _is_minor(c))
    if not unknown and not repeated and not contrast and not inferred and len(majors) <= 1:
        return ScorePrediction(
            estimate, "medium",
            "Ally has not scored this exact combination, but it has scored each of these issues, "
            "and minor issues have always lowered the score by a fixed amount.",
        )
    reasons = []
    for code in repeated:
        reasons.append(f"{_name(code)} occurs {counts[code]} times, but the test PDFs had only one, "
                       "so whether Ally charges per occurrence is unknown")
    if len(majors) > 1:
        reasons.append(f"how several major issues ({_names(majors)}) combine is based on only two test PDFs")
    if little_text:
        reasons.append("only a little text has low contrast; Ally charged almost nothing for 4 such characters "
                       "in an 18-page PDF, but how the cost grows with the amount of such text is untested")
    elif contrast:
        if page_count and 1 < page_count <= 3:
            reasons.append(f"the contrast penalty shrinks with length; on {page_count}-page documents it rests on two test PDFs")
        elif page_count:
            reasons.append(f"the contrast penalty shrinks with length, and was measured only on 1-3 page documents (this one has {page_count} pages with text)")
        else:
            reasons.append("the contrast penalty depends on the number of pages with text, which could not be determined")
    for code in inferred:
        reasons.append(f"the cost of {_name(code)} was measured, but which Ally check reports it is a guess")
    if unknown:
        reasons.append(f"Ally has not yet scored {_names(unknown)}, so those issues are left out")
    spread = 8 + 4 * max(0, sum(counts.values()) - 2) + 5 * len(unknown)
    lower = estimate - spread
    if little_text:
        # In case a little low-contrast text costs as much as a page of it.
        lower = min(lower, estimate_score(known, page_count))
    return ScorePrediction(
        estimate, "low",
        "Estimated from what each issue cost on its own in Ally tests. It is uncertain because "
        + "; ".join(reasons) + ".",
        max(SCORE_FLOOR, lower), min(100, estimate + spread),
    )


def _counts(findings: list[Finding]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for finding in findings:
        if finding.ally_code in CHARGED_ONCE:
            counts[finding.ally_code] = 1
        elif finding.ally_code:
            counts[finding.ally_code] += max(1, finding.occurrences)
    return counts


def _contrast_scale(findings: list[Finding]) -> float | None:
    return next((x.scale for x in findings if x.ally_code == "Contrast:2"), None)


def predict_score(findings: list[Finding], page_count: int | None = 1) -> ScorePrediction:
    counts = _counts(findings)
    scale = _contrast_scale(findings)
    prediction = _predict(counts, page_count, scale)
    # Like Ally's "Increase score up to N%": the score with only that issue fixed.
    if prediction.score is not None:
        for code in counts:
            rest = counts.copy()
            del rest[code]
            fixed = _predict(rest, page_count, scale).score
            if fixed is not None:
                prediction.score_if_fixed[code] = fixed
    return prediction
