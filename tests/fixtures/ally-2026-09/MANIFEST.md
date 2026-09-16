# Anthology Ally PDF test corpus

Generated with LuaLaTeX 1.24.0 / LaTeX 2026 using the modern `DocumentMetadata` and `tagpdf` test-phase tagging mechanism where applicable. The observed results below were collected from Ally in Canvas on 2026-09-16.

“Documented” means the expected issue exists in Anthology's published PDF checklist. “Experimental” means the file probes an implementation detail whose exact Ally behavior is not publicly specified. Other incidental flags can still occur, especially on deliberately untagged scan/OCR cases.

| File | Controlled property | Expected Ally result | Confidence |
|---|---|---|---|
| `01_tagged_baseline.pdf` | Tagged positive control with title, `en-US`, H1 then H2, selectable text | No target issue | Experimental positive control |
| `02_untagged.pdf` | Selectable text and visible heading, but no structure tree | `Tagged` / PDF is untagged (Major) | Documented |
| `03_tagged_no_title.pdf` | Same tagged style, but `/Title` omitted | `Title` / no document title (Minor) | Documented |
| `04_tagged_no_language.pdf` | Same tagged style, but catalog `/Lang` omitted | `LanguagePresence` / no language set (Minor) | Documented |
| `05_no_headings_2_pages.pdf` | Tagged, two pages, only bold visual labels - no H tags | No headings-presence issue because fewer than 3 pages | Documented threshold; result is a boundary test |
| `06_no_headings_3_pages.pdf` | Tagged, three pages, only bold visual labels - no H tags | `HeadingsPresence` / no headings (Major) | Documented at >=3 pages |
| `07_first_heading_h2.pdf` | First and only heading is H2 | `HeadingsStartAtOne` / does not start at H1 (Minor) | Documented |
| `08_skipped_heading_level.pdf` | H1 followed directly by H3 | `HeadingsSequential` / inappropriate heading structure (Minor) | Documented |
| `09_sequential_headings.pdf` | H1, H2, H3 sequence | No heading-structure issue | Experimental positive control |
| `10_heading_beyond_h6.pdf` | Experimental literal H7 structure element, role-mapped to H6 for PDF validity | Possibly `HeadingsHigherLevel` / beyond H6 (Minor) | Experimental: Ally may honor the role map and treat it as H6 |
| `11_figure_with_alt.pdf` | Figure tag with meaningful `/Alt` text | No alternative-text issue | Experimental positive control |
| `12_figure_without_alt.pdf` | Figure tag with `/Alt` deliberately removed after LaTeX compilation | `AlternativeText` / image lacks description (Major) | Documented check; minimal post-process noted below |
| `13_table_with_headers.pdf` | Tagged table with first row marked as `TH` cells | No table-header issue | Experimental positive control |
| `14_table_without_headers.pdf` | Tagged table whose first row remains ordinary `TD` cells | `TableHeaders` / table lacks headers (Major) | Documented check |
| `15_image_only_scan.pdf` | Untagged page containing only a rasterized LaTeX page; no extractable text | `Scanned` (Severe), likely also `Tagged` | Documented check; combination expected |
| `16_image_with_hidden_text_layer.pdf` | Same raster page plus an invisible extractable text layer, approximating OCR | Likely `Ocred` (Major) and `Tagged`; exact classification versus `Scanned` is uncertain | Experimental OCR heuristic probe |

## Observed Ally results

| File | Score | Displayed issue code(s) |
|---|---:|---|
| `01_tagged_baseline.pdf` | 100 | None |
| `02_untagged.pdf` | 12 | `Tagged:2` |
| `03_tagged_no_title.pdf` | 98 | `Title:3` |
| `04_tagged_no_language.pdf` | 95 | `LanguagePresence:3` |
| `05_no_headings_2_pages.pdf` | 100 | None |
| `06_no_headings_3_pages.pdf` | 54 | `HeadingsPresence:2` |
| `07_first_heading_h2.pdf` | 95 | `HeadingsStartAtOne:3` |
| `08_skipped_heading_level.pdf` | 98 | `HeadingsSequential:3` |
| `09_sequential_headings.pdf` | 100 | None |
| `10_heading_beyond_h6.pdf` | 98 | `HeadingsHigherLevel:3` (inferred from the controlled property and one-issue course summary) |
| `11_figure_with_alt.pdf` | 100 | None |
| `12_figure_without_alt.pdf` | 54 | `AlternativeText:2` |
| `13_table_with_headers.pdf` | 100 | None |
| `14_table_without_headers.pdf` | 69 | `TableHeaders:2` |
| `15_image_only_scan.pdf` | 6 | `Tagged:2`, `LanguagePresence:3`, `Title:3` |
| `16_image_with_hidden_text_layer.pdf` | 5 | `Contrast:2`, `Tagged:2`, `LanguagePresence:3`, `Title:3` |

Notably, Ally did not classify files 15 or 16 as `Scanned` or `Ocred`. File 16's white text layer instead triggered `Contrast:2`. This is why `pdfcheck` does not implement a naive full-page-image rule as an Ally scan prediction.

## Construction notes

- Files 01 and 03-14 use modern LaTeX tagging. File 02 is a conventional untagged LuaLaTeX PDF.
- File 04 is compiled by LaTeX, then only the default `/Lang` catalog entry automatically supplied by current LaTeX is removed.
- File 12 is compiled by LaTeX, then only the fallback `/Alt` entry automatically supplied by current LaTeX is removed. This is necessary because current LaTeX inserts the image filename when alt text is omitted.
- Files 15 and 16 rasterize a separate LaTeX-generated page and embed that PNG in a new LuaLaTeX PDF. File 16 adds white extractable text to mimic an OCR text layer; it is not produced by an OCR engine.
- The LaTeX sources and image assets are in `latex_sources/`. The reproducible builder and verifier are under `tools/`.

## Suggested result capture

For each upload, record: filename, Ally score, every issue code/label, severity, whether an alternative format is offered, and any delay before the report stabilizes. Do not infer a check's absence from score alone; capture the issue list explicitly.
