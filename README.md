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
- probable scan (`Scanned:1`, low confidence): every page is a single image covering at least 90% of the page with no visible text. Ally scored such files 0 but did not flag a LaTeX page whose image covered 58%
- no headings in PDFs of at least three pages (`HeadingsPresence:2`)
- first heading not H1 (`HeadingsStartAtOne:3`)
- skipped heading level (`HeadingsSequential:3`)
- heading level beyond H6 (`HeadingsHigherLevel:3`)
- missing Figure alternative text, including a filename such as `figure.png` (`AlternativeText:2`)
- tagged tables without TH cells (`TableHeaders:2`)
- low-contrast text (`Contrast:2`): computes the WCAG contrast ratio of each painted text colour against an assumed white page and flags anything below 4.5:1. It understands `g`/`rg`/`k`, `cs`/`scn` with Gray/RGB/CMYK/ICC colour spaces, fill transparency, and text inside form XObjects, and ignores invisible OCR text (render mode 3). Ally's threshold matched WCAG in October 2026 probes: #808080 (3.9:1) was flagged and #767676 (4.5:1) was not

Role maps are resolved, so modern LaTeX structure names such as `/section` mapped to `/H1` are understood. A literal `/H7` remains detectable even when role-mapped to `/H6`, matching the observed Ally result.

## Ally score model

Calibration so far (38 Ally observations, September and October 2026) supports a simple model:

- **Point losses add.** Each issue costs what it cost alone (for example untagged 88, missing language 5), and combinations subtract the sum from 100. Every observed combination matched exactly, apart from fixture 15 (predicted 5, observed 6). Multiplying score ratios was ruled out.
- **The score does not fall below 5** unless there is a severe issue. Grey text plus a missing alt text would add up to well below zero but scored 5.
- **A scanned PDF scores 0.**
- **Contrast is the exception:** it cost 95 points on a one-page file but about 48 on a two-page file, whether one page or both were grey. The tool currently divides the contrast loss by page count, which fits those two files only (low confidence; batch `ally-2026-10b` tests it).

Exact matches to an observed file report medium confidence; so do unobserved combinations of issues with known single scores. Repeated issues (for example two images without alt text), page-count-dependent contrast, inferred codes and uncalibrated issues are low confidence and show a range.

## Full audit

The initial full mode adds probable image-only-page detection, multi-page heading guidance, title-quality checks, filename-like alt-text detection, and a manual-review checklist. It also reports enhanced checks that were unavailable in the current installation.

## Known limitations and TODOs

- Pin down Ally's `Scanned:1` image-coverage threshold (between 58% and 100%) and reproduce `Ocred:2`. A full-page image with an invisible OCR layer still scored 0.
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
- `ally-2026-10b/`: 8 follow-ups on the contrast page-count effect, the scan threshold, and the alt-text filename rule.

1. Upload the PDFs to a Canvas course where Ally is enabled (an unpublished sandbox course is fine).
2. Wait for Ally to finish processing, then open each file's Ally indicator.
3. Record the score and every issue shown in that batch's `results.csv`. The issue codes matter: several October results could only be inferred from the score.

The newest batch can be regenerated without LaTeX: `python tools/build_probe_batch.py` (requires Pillow). Existing `results.csv` files are never overwritten.

## Contributing

Bug reports, additional Ally observations, narrowly controlled fixtures, and code contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). When reporting an Ally mismatch, include the PDF if it can be shared, the observed score, every displayed issue, and the processing date.

## License

MIT. See [LICENSE](LICENSE). Anthology, Ally, and Canvas are trademarks of their respective owners. This project is independent and unofficial.
