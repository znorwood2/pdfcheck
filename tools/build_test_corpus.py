from pathlib import Path
import os, subprocess, shutil, textwrap
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "pdfs"
OUT = ROOT / "tests" / "fixtures" / "ally-2026-09"
SRC = OUT / "latex_sources"
for p in (TMP, OUT, SRC): p.mkdir(parents=True, exist_ok=True)

def run(cmd, cwd=TMP):
    env = os.environ.copy()
    cache = TMP / ".texlive-cache"
    cache.mkdir(parents=True, exist_ok=True)
    env.update({"TEXMFVAR": str(cache), "TEXMFCACHE": str(cache)})
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout[-4000:] + result.stderr[-4000:])

def compile_tex(name, body, *, tagged=True, title="Ally Test Document", lang="en-US", setup=""):
    metadata = ""
    if tagged:
        opts = ["testphase=latest"]
        if lang: opts.append(f"lang={lang}")
        metadata = "\\DocumentMetadata{" + ",".join(opts) + "}\n"
    pre = metadata + r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx,xcolor,array,hyperref}
\setlength{\parindent}{0pt}
\setlength{\parskip}{8pt}
"""
    if title is not None:
        pre += "\\hypersetup{pdftitle={" + title + "}}\n"
    if (not tagged) and lang:
        pre += "\\hypersetup{pdfsubject={Controlled Ally test case}}\n"
        pre += "\\pdfcatalog{/Lang (" + lang + ")}\n"
    tex = pre + setup + "\n\\begin{document}\n" + body + "\n\\end{document}\n"
    tex_path = SRC / f"{name}.tex"
    tex_path.write_text(tex)
    work_tex = TMP / tex_path.name
    shutil.copy2(tex_path, work_tex)
    run(["lualatex", "-interaction=nonstopmode", "-halt-on-error", work_tex.name])
    run(["lualatex", "-interaction=nonstopmode", "-halt-on-error", work_tex.name])
    shutil.copy2(TMP / f"{name}.pdf", OUT / f"{name}.pdf")

filler = ("This controlled document contains ordinary selectable text. "
          "It is designed to isolate one accessibility property for Anthology Ally testing. ")

# A raster asset used for controlled Figure tests.
im = Image.new("RGB", (1200, 500), "white")
d = ImageDraw.Draw(im)
d.rectangle((80, 80, 1120, 420), fill="#dcecff", outline="#185a9d", width=8)
d.ellipse((180, 145, 430, 355), fill="#f6b44b", outline="#7a4300", width=6)
d.text((510, 210), "CONTROLLED TEST FIGURE", fill="#14213d", font=None)
asset = TMP / "test-figure.png"
im.save(asset)
shutil.copy2(asset, SRC / asset.name)

compile_tex("01_tagged_baseline", r"""\section{Introduction}
This is the positive control. It has a title, language, tags, an H1-equivalent section, and selectable text.
\subsection{Details}
The heading hierarchy proceeds from level one to level two.""")

compile_tex("02_untagged", r"""\section{Introduction}
This negative control has normal selectable text and visible headings but no PDF structure tree.""", tagged=False)

compile_tex("03_tagged_no_title", r"""\section{Introduction}
This tagged document deliberately omits the PDF title metadata field.""", title=None)

compile_tex("04_tagged_no_language", r"""\section{Introduction}
This tagged document deliberately omits document language metadata.""", lang=None)

# Current LaTeX supplies a default English /Lang even when none is requested.
# Remove only that catalog entry for the controlled missing-language case.
no_lang = OUT / "04_tagged_no_language.pdf"
reader = PdfReader(no_lang)
writer = PdfWriter(); writer.clone_document_from_reader(reader)
writer.root_object.pop("/Lang", None)
with no_lang.open("wb") as f: writer.write(f)

two_pages = (r"\textbf{Visual label only, not a tagged heading.}\par " + filler*8 +
             r"\newpage\textbf{Second visual label only.}\par " + filler*8)
compile_tex("05_no_headings_2_pages", two_pages)

three_pages = two_pages + r"\newpage\textbf{Third visual label only.}\par " + filler*8
compile_tex("06_no_headings_3_pages", three_pages)

compile_tex("07_first_heading_h2", r"""\setcounter{section}{0}
\subsection{Starts at level two}
The first tagged heading is deliberately H2, with no preceding H1.""")

compile_tex("08_skipped_heading_level", r"""\section{Level one heading}
Introductory text.
\subsubsection{Level three heading}
This deliberately skips level two.""")

compile_tex("09_sequential_headings", r"""\section{Level one heading}
Introductory text.
\subsection{Level two heading}
This is the positive heading-structure control.
\subsubsection{Level three heading}
The levels remain sequential.""")

compile_tex("10_heading_beyond_h6", r"""\section{Level one heading}
\tagstructbegin{tag=H7}\tagmcbegin{}Level seven experimental heading\tagmcend\tagstructend

This structure element is deliberately named H7 to probe Ally's beyond-H6 check.""",
            setup=r"\tagpdfsetup{role/new-tag=H7/H6}")

compile_tex("11_figure_with_alt", r"""\section{Figure with alternative text}
\begin{figure}[h]
\centering\includegraphics[width=.72\linewidth,alt={A blue rectangle containing an orange circle and the words Controlled Test Figure}]{test-figure.png}
\caption{Controlled figure with alt text}
\end{figure}""")

compile_tex("12_figure_without_alt", r"""\section{Figure without alternative text}
\begin{figure}[h]
\centering\includegraphics[width=.72\linewidth]{test-figure.png}
\caption{Controlled figure lacking alt text}
\end{figure}""")

# Current LaTeX helpfully inserts the filename as fallback alt text. Remove only
# that /Alt entry so this remains a controlled missing-alt negative case.
no_alt = OUT / "12_figure_without_alt.pdf"
reader = PdfReader(no_alt)
def strip_alt(node):
    obj = node.get_object()
    if obj.get("/S") == "/Figure": obj.pop("/Alt", None)
    kids = obj.get("/K", [])
    if not isinstance(kids, list): kids = [kids]
    for kid in kids:
        try:
            if hasattr(kid.get_object(), "get") and kid.get_object().get("/Type") == "/StructElem": strip_alt(kid)
        except Exception:
            pass
root = reader.trailer["/Root"].get("/StructTreeRoot")
if root: strip_alt(root)
writer = PdfWriter(); writer.clone_document_from_reader(reader)
with no_alt.open("wb") as f: writer.write(f)

compile_tex("13_table_with_headers", r"""\section{Table with header cells}
\tagpdfsetup{table/header-rows={1}}
\begin{tabular}{|l|r|}\hline
Category & Count \\\hline
Apples & 4 \\
Pears & 7 \\\hline
\end{tabular}""")

compile_tex("14_table_without_headers", r"""\section{Table without header cells}
\begin{tabular}{|l|r|}\hline
Category & Count \\\hline
Apples & 4 \\
Pears & 7 \\\hline
\end{tabular}""")

# Produce a clean one-page LaTeX page, rasterize it, then wrap that raster in LaTeX.
compile_tex("_scan_source", r"""\section{Scanned handout}
This sentence exists only to create the source image. The delivered scan case contains pixels, not this text layer.
\vspace{1cm}
\Large Name: \rule{7cm}{0.4pt}\par
\Large Date: \rule{7cm}{0.4pt}""", tagged=False)
run(["pdftoppm", "-f", "1", "-singlefile", "-r", "180", "-png", str(OUT / "_scan_source.pdf"), "scan-page"])
scan_png = TMP / "scan-page.png"
shutil.copy2(scan_png, SRC / scan_png.name)
compile_tex("15_image_only_scan", r"""\thispagestyle{empty}
\noindent\includegraphics[width=\textwidth,height=.92\textheight]{scan-page.png}""", tagged=False,
            setup=r"\usepackage[absolute,overlay]{textpos}", lang=None, title=None)

compile_tex("16_image_with_hidden_text_layer", r"""\thispagestyle{empty}
\noindent\makebox[0pt][l]{\color{white}Scanned handout. This sentence represents an OCR text layer. Name. Date.}%
\includegraphics[width=\textwidth,height=.92\textheight]{scan-page.png}""", tagged=False,
            setup=r"\usepackage[absolute,overlay]{textpos}", lang=None, title=None)

# Remove the intermediate PDF from the deliverable set; its TeX remains for provenance.
(OUT / "_scan_source.pdf").unlink()
print("Built 16 PDFs in", OUT)
