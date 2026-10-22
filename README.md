# pdfcheck

`pdfcheck` has two deliberately different modes:

```bash
pdfcheck --canvas handout.pdf
pdfcheck --full handout.pdf
```

- `--canvas` predicts Anthology Ally issue codes and an empirical Ally score.
- `--full` performs broader checks, distinguishes evidence from heuristics, and supplies a manual-review checklist.

This is an early implementation calibrated against 16 controlled LuaLaTeX PDFs processed by Ally in Canvas on 2026-09-16. It is not affiliated with or endorsed by Anthology.

## Installation

From this source directory:

```bash
python -m pip install -e .
```

The core requires Python 3.10+ and `pypdf`. No PDF renderer or platform-specific executable is currently required. A rendering backend will be selected deliberately after comparing portability, licensing, and fidelity; the CLI reports rendering-dependent checks as skipped in the meantime.

The package can also be run without installation:

```bash
python -m pdfcheck --canvas tests/fixtures/ally-2026-09/12_figure_without_alt.pdf
```

## Output

Human-readable terminal output is the default. JSON is available for regression testing and integrations:

```bash
pdfcheck --canvas --json report.json handout.pdf
pdfcheck --full --json - handout.pdf
```

Exit status is `1` when a Severe or Major automated finding is present, otherwise `0`.

## Implemented Canvas checks

- malformed/unparsable PDF (`Parsable:1`)
- encryption (`Security:1`)
- missing structure tree (`Tagged:2`)
- missing title (`Title:3`)
- missing language (`LanguagePresence:3`)
- no headings in PDFs of at least three pages (`HeadingsPresence:2`)
- first heading not H1 (`HeadingsStartAtOne:3`)
- skipped heading level (`HeadingsSequential:3`)
- heading level beyond H6 (`HeadingsHigherLevel:3`)
- missing Figure alternative text (`AlternativeText:2`)
- tagged tables without TH cells (`TableHeaders:2`)
- low-contrast text (`Contrast:2`): computes the WCAG contrast ratio of each painted text colour against an assumed white page and flags anything below 4.5:1. It understands `g`/`rg`/`k`, `cs`/`scn` with Gray/RGB/CMYK/ICC colour spaces, fill transparency, and text inside form XObjects, and ignores invisible OCR text (render mode 3). Near-white text (below 1.5:1) is medium confidence because Ally flagged it in calibration; mid-grey text is low confidence until Ally's own threshold is observed

Role maps are resolved, so modern LaTeX structure names such as `/section` mapped to `/H1` are understood. A literal `/H7` remains detectable even when role-mapped to `/H6`, matching the observed Ally result.

## Ally score model

Issue sets and occurrence counts matching an observed specimen receive its score as a medium-confidence estimate. They are not labeled high confidence because Ally may also use document composition. At present the calibration data includes all single-issue PDFs and the two observed multi-issue image-wrapper PDFs.

Repeated instances and unseen combinations get a low-confidence estimate: 100 minus the sum of each issue's observed single-issue point loss. On the one observed combination whose parts all have known single scores (untagged + no title + no language, Ally score 6), subtraction predicts 5 and multiplying the score ratios predicts 11. The displayed range covers both methods. Issues without a calibrated single score (currently `Contrast:2`) only widen the range.

Score calibration is separate from issue detection. This matters because Ally's formula is unpublished and appears to depend on document composition as well as issue types.

## Full audit

The initial full mode adds probable image-only-page detection, multi-page heading guidance, title-quality checks, filename-like alt-text detection, and a manual-review checklist. It also reports enhanced checks that were unavailable in the current installation.

## Known limitations and TODOs

- Reproduce Ally's `Scanned:1` and `Ocred:2` classifiers. A full-page raster wrapped by LuaLaTeX did not trigger either issue in the calibration run, so a naïve “image plus no text means Ally Scanned” rule would be wrong.
- Implement `LanguageCorrect:3` with enough text and an explicit confidence threshold.
- Replace the contrast operator heuristic with rendered foreground/background analysis. White text can be valid on a dark background, and text inside images is not checked.
- Read the XMP `dc:title` if Ally turns out to accept it (probe `M01`). PDF 2.0 deprecates the Info dictionary, so some exporters write only XMP.
- Select a cross-platform rendering/geometry backend after reviewing fidelity and licensing, then add reading-order, overlap, clipping, contrast, and effective-resolution checks.
- Validate table header scope and irregular or spanning table cells.
- Inspect link purpose, form-field labels and tab order, font embedding, and character mappings.
- Add an optional veraPDF adapter for formal PDF/UA validation.
- Add optional Tesseract comparison of visible content against existing OCR text.
- Generate HTML reports with page thumbnails and highlighted evidence.
- Expand score calibration with controlled two-issue and repeated-issue PDFs. The October 2026 probe batch covers combinations that can be made by editing existing fixtures; repeated issues (for example two figures, one missing alt text) still need new LaTeX sources.

## Tests

The checked-in corpus is the executable specification for current Ally compatibility:

```bash
python -m unittest discover -s tests -v
```

The regression test requires all 16 predicted issue sets and scores to match the observations copied from Canvas and confirmed by the supplied screenshots.

## Repository layout

```text
pdfcheck/                         application package
tests/                            unit and CLI tests
tests/fixtures/ally-2026-09/      compact controlled PDF corpus
tools/build_test_corpus.py        reproducible LuaLaTeX corpus builder
tools/verify_corpus.py            structural fixture summary
tools/build_probe_batch.py        builds the next Ally calibration batch from the corpus
probes/ally-2026-10/              generated probe PDFs awaiting Ally results
```

The original Canvas screenshots are intentionally not included. The fixture manifest records the observed scores and expected issue codes without publishing course-interface captures.

Rebuilding the corpus requires LuaLaTeX, Poppler's `pdftoppm`, and the optional Python corpus dependencies:

```bash
python -m pip install -e '.[corpus]'
python tools/build_test_corpus.py
```

## Collecting more Ally observations

`probes/ally-2026-10/` holds 22 PDFs, each a copy of a scored fixture with one property changed. They answer the open questions that most limit prediction accuracy: Ally's contrast threshold and penalty, whether issue penalties add or multiply, which title and language metadata Ally reads, what counts as tagged, whether filename alt text passes, and what triggers `Scanned` and `Ocred`. `PROBES.md` lists each question and pdfcheck's current prediction.

1. Upload the PDFs to a Canvas course where Ally is enabled (an unpublished sandbox course is fine).
2. Wait for Ally to finish processing, then open each file's Ally indicator.
3. Record the score and every issue shown in `probes/ally-2026-10/results.csv`.

The files can be regenerated without LaTeX: `python tools/build_probe_batch.py` (requires Pillow).

## Contributing

Bug reports, additional Ally observations, narrowly controlled fixtures, and code contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). When reporting an Ally mismatch, include the PDF if it can be shared, the observed score, every displayed issue, and the processing date.

## License

MIT. See [LICENSE](LICENSE). Anthology, Ally, and Canvas are trademarks of their respective owners. This project is independent and unofficial.
