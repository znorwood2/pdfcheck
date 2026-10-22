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
- missing or empty structure tree (`Tagged:2`; Ally treats an empty tag tree as untagged)
- missing title (`Title:3`; Ally reads the Info dictionary `/Title`, so an XMP-only title still fails)
- missing language (`LanguagePresence:3`)
- invalid or mismatched language (`LanguageCorrect:3`, low confidence): a value that is not a language code, or a declared language that disagrees with a function-word guess for English, Spanish, French, German, Italian, Portuguese or Dutch text. The score effect is observed; the code Ally displays has not been recorded yet
- probable scan (`Scanned:1`, low confidence): an untagged PDF where every page is mostly one image (at least 65% of the page) with under about 200 visible characters. Ally scored such files 0 at 70%, 80% and 100% coverage, even with an invisible OCR layer or a visible footer; it did not flag 58% coverage (PNG or JPEG), or a tagged handout whose figure covered 85%
- no headings in PDFs of at least three pages (`HeadingsPresence:2`)
- first heading not H1 (`HeadingsStartAtOne:3`)
- skipped heading level (`HeadingsSequential:3`)
- heading level beyond H6 (`HeadingsHigherLevel:3`)
- missing Figure alternative text, including a filename such as `figure.png` (`AlternativeText:2`)
- tagged tables without TH cells (`TableHeaders:2`); one-cell tables are skipped because Ally did not flag one
- low-contrast text (`Contrast:2`): computes the WCAG contrast ratio of each painted text colour against an assumed white page and flags anything below 4.5:1. It understands `g`/`rg`/`k`, `cs`/`scn` with Gray/RGB/CMYK/ICC colour spaces, fill transparency, and text inside form XObjects, and ignores invisible OCR text (render mode 3). Ally's threshold matched WCAG in October 2026 probes: #808080 (3.9:1) was flagged and #767676 (4.5:1) was not

Role maps are resolved, so modern LaTeX structure names such as `/section` mapped to `/H1` are understood. A literal `/H7` remains detectable even when role-mapped to `/H6`, matching the observed Ally result.

## Ally score model

Calibration so far (53 Ally scores plus the "Increase score up to" figures from two screenshots, September and October 2026) fits this model, to within the 1-point drift Ally shows between files with the same issues:

- **Minor issues subtract.** Each minor (severity 3) issue costs the points it cost alone: missing title 2, missing language 5. Untagged plus no language scored 12 − 5 = 7; missing alt text plus no title and no language scored 54 − 2 − 5 = 47. Multiplying did not fit these.
- **Major issues multiply.** Missing headings (54) plus grey text on three pages scored 54 × 0.68 = 37; subtracting predicted 22. This rests on one observation and is low confidence until batch `ally-2026-10d` confirms it.
- **The score does not fall below 5** unless there is a severe issue, and a scanned PDF scores 0.
- **Contrast scales with page count:** grey text cost 95 points on one page, about 48 on two and 32–33 on three, however many of the pages were grey. The tool divides the loss by page count.
- **Ally's "Increase score up to N%" figures** (shown under each issue) give the score with that one issue fixed. Those recorded so far match the model.

Exact matches to an observed file, and combinations of one calibrated major issue with minor issues, report medium confidence. Several major issues, repeated issues (for example two images without alt text), multi-page contrast, inferred codes and uncalibrated issues are low confidence and show a range.

## Full audit

The initial full mode adds probable image-only-page detection, multi-page heading guidance, title-quality checks, filename-like alt-text detection, and a manual-review checklist. It also reports enhanced checks that were unavailable in the current installation.

## Known limitations and TODOs

- Pin down what Ally's `Scanned:1` keys on and reproduce `Ocred:2`. A full-page image with an invisible OCR layer still scored 0.
- Replace the function-word language guess with a proper detector if real documents produce false `LanguageCorrect:3` results.
- Replace the contrast operator heuristic with rendered foreground/background analysis. White text can be valid on a dark background, and text inside images is not checked.
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
probes/                           probe batches and their recorded Ally results
```

The original Canvas screenshots are intentionally not included. The fixture manifest records the observed scores and expected issue codes without publishing course-interface captures.

Rebuilding the corpus requires LuaLaTeX, Poppler's `pdftoppm`, and the optional Python corpus dependencies:

```bash
python -m pip install -e '.[corpus]'
python tools/build_test_corpus.py
```

## Collecting more Ally observations

Each folder under `probes/` is a batch of PDFs, each a copy of a scored fixture with one property changed. `PROBES.md` lists each question, pdfcheck's prediction and, once recorded, Ally's result. Filled-in `results.csv` files are run as regression tests by `tests/test_probe_results.py`.

- `ally-2026-10/`: 22 probes, results recorded 2026-10-21.
- `ally-2026-10b/`: 8 follow-ups on contrast and page count, the scan threshold, and the alt-text filename rule; results recorded.
- `ally-2026-10c/`: 7 probes on contrast over three pages and what triggers `Scanned`; results and two screenshots recorded. Ally ignored the one-cell table in X01.
- `ally-2026-10d/`: 5 probes using a real 2x2 table to test whether major issues multiply and whether TableHeaders or Tagged scale with page count.

1. Upload the PDFs to a Canvas course where Ally is enabled (an unpublished sandbox course is fine).
2. Wait for Ally to finish processing, then click each file's Ally score indicator (the small gauge icon next to the file name) to open its feedback window. The issues are listed there; if only one is shown, look for an option to view all issues.
3. Record the score in that batch's `results.csv`. In the `ally_issue_codes` column, paste the issue descriptions Ally lists for the file, separated by `;` (for example `This PDF is untagged; This PDF does not have a title`), or `none`. Ally shows instructors descriptions, not codes; `tests/ally_issue_text.py` translates them. If the tests report an unrecognized description, add a keyword rule there.
4. Optionally, record the "Increase score up to N%" figure shown under each issue in the `ally_fix_scores` column, as `<issue description> N`, separated by `;`. Each figure is a free extra observation.

The newest batch can be regenerated without LaTeX: `python tools/build_probe_batch.py` (requires Pillow). Existing `results.csv` files are never overwritten.

## Contributing

Bug reports, additional Ally observations, narrowly controlled fixtures, and code contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). When reporting an Ally mismatch, include the PDF if it can be shared, the observed score, every displayed issue, and the processing date.

## License

MIT. See [LICENSE](LICENSE). Anthology, Ally, and Canvas are trademarks of their respective owners. This project is independent and unofficial.
