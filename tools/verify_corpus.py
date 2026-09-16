from pathlib import Path
from pypdf import PdfReader

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ally-2026-09"

def walk(node, tags, alts):
    try: obj = node.get_object()
    except Exception: return
    if not hasattr(obj, "get"): return
    s = obj.get("/S")
    if s:
        tags.append(str(s))
        if str(s) == "/Figure": alts.append(obj.get("/Alt"))
    kids = obj.get("/K", [])
    if not isinstance(kids, list): kids = [kids]
    for kid in kids: walk(kid, tags, alts)

for pdf in sorted(OUT.glob("[0-9][0-9]_*.pdf")):
    r = PdfReader(pdf)
    root = r.trailer["/Root"]
    tags, alts = [], []
    if root.get("/StructTreeRoot"): walk(root["/StructTreeRoot"], tags, alts)
    images = sum(len(p.images) for p in r.pages)
    chars = sum(len(p.extract_text() or "") for p in r.pages)
    rolemap = root.get("/StructTreeRoot", {}).get_object().get("/RoleMap", {}) if root.get("/StructTreeRoot") else {}
    headings = [str(rolemap.get(t, t)) for t in tags if str(rolemap.get(t, t)).startswith("/H")]
    print(f"{pdf.name}|pages={len(r.pages)}|title={r.metadata.title!r}|lang={root.get('/Lang')!r}|"
          f"struct={bool(tags)}|headings={headings}|fig_alt={alts}|TH={tags.count('/TH')}|"
          f"images={images}|textchars={chars}")
