from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.generic import ContentStream

from .model import DocumentFacts, StructureElement


def _name(value: Any) -> str:
    try:
        value = value.get_object()
    except Exception:
        pass
    if value is None or value.__class__.__name__ == "NullObject":
        return ""
    return str(value)


def _text(value: Any) -> str | None:
    rendered = _name(value).strip()
    return rendered or None


def _resolve_role(raw: str, rolemap: dict[str, Any]) -> str:
    """Resolve chained role mappings while tolerating malformed cycles."""
    current = raw
    seen: set[str] = set()
    while current in rolemap and current not in seen:
        seen.add(current)
        current = _name(rolemap[current])
    return current


def _walk_structure(
    node: Any,
    rolemap: dict[str, Any],
    output: list[StructureElement],
    seen: set[tuple[Any, ...]],
    table_headers: list[bool],
    active_table: int | None = None,
    table_cells: list[int] | None = None,
    table_rows: list[int] | None = None,
) -> None:
    try:
        obj = node.get_object()
    except Exception:
        return
    if not hasattr(obj, "get"):
        return
    try:
        object_key: tuple[Any, ...] = ("indirect", node.idnum, node.generation)
    except Exception:
        object_key = ("direct", id(obj))
    if object_key in seen:
        return
    seen.add(object_key)
    raw = _name(obj.get("/S"))
    if raw:
        resolved = _resolve_role(raw, rolemap)
        output.append(StructureElement(raw_tag=raw, resolved_tag=resolved, alt=_text(obj.get("/Alt"))))
        if resolved == "/Table":
            active_table = len(table_headers)
            table_headers.append(False)
            if table_cells is not None:
                table_cells.append(0)
            if table_rows is not None:
                table_rows.append(0)
        elif resolved == "/TR" and active_table is not None:
            if table_rows is not None:
                table_rows[active_table] += 1
        elif resolved in {"/TH", "/TD"} and active_table is not None:
            if resolved == "/TH":
                table_headers[active_table] = True
            if table_cells is not None:
                table_cells[active_table] += 1
    children = obj.get("/K", [])
    if not isinstance(children, list):
        children = [children]
    for child in children:
        _walk_structure(child, rolemap, output, seen, table_headers, active_table, table_cells, table_rows)


def _srgb_to_linear(channel: float) -> float:
    channel = min(1.0, max(0.0, channel))
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(r: float, g: float, b: float) -> float:
    """WCAG 2.x relative luminance of an sRGB colour."""
    return 0.2126 * _srgb_to_linear(r) + 0.7152 * _srgb_to_linear(g) + 0.0722 * _srgb_to_linear(b)


def _rgb_from_components(values: list[float]) -> tuple[float, float, float] | None:
    if len(values) == 1:
        return values[0], values[0], values[0]
    if len(values) == 3:
        return values[0], values[1], values[2]
    if len(values) == 4:
        c, m, y, k = values
        return 1 - min(1, c + k), 1 - min(1, m + k), 1 - min(1, y + k)
    return None


def _colour_space_components(name: str, resources: Any) -> int | None:
    """Number of components when a colour space behaves like Gray/RGB/CMYK.

    Separation, DeviceN, Indexed and Pattern spaces return None: their
    components are not lightness values, so guessing would invert results.
    """
    direct = {"/DeviceGray": 1, "/G": 1, "/DeviceRGB": 3, "/RGB": 3, "/DeviceCMYK": 4, "/CMYK": 4}
    if name in direct:
        return direct[name]
    try:
        spaces = resources.get("/ColorSpace").get_object()
        space = spaces.get(name).get_object()
    except Exception:
        return None
    try:
        if not isinstance(space, list):
            return direct.get(_name(space))
        family = _name(space[0])
        if family == "/ICCBased":
            return int(space[1].get_object().get("/N"))
        if family in {"/CalGray", "/CalRGB"}:
            return 1 if family == "/CalGray" else 3
    except Exception:
        return None
    return None


def _contrast_against_white(rgb: tuple[float, float, float], alpha: float) -> float:
    # Composite partially transparent text over a white page before comparing.
    r, g, b = (alpha * c + (1 - alpha) for c in rgb)
    return 1.05 / (_relative_luminance(r, g, b) + 0.05)


_TEXT_SHOWING = {"Tj", "TJ", "'", '"'}


def _multiply(a: list[float], b: list[float]) -> list[float]:
    """Product of two PDF affine matrices [a b c d e f] (a applied first)."""
    return [
        a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5],
    ]


def _unit_square_bbox(ctm: list[float]) -> tuple[float, float, float, float]:
    points = [(ctm[4] + x * ctm[0] + y * ctm[2], ctm[5] + x * ctm[1] + y * ctm[3]) for x, y in ((0, 0), (1, 0), (0, 1), (1, 1))]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


class _PageScan:
    """What one pass over a page's content found."""

    def __init__(self) -> None:
        self.lowest_contrast: float | None = None
        self.visible_text_chars = 0
        self.image_boxes: list[tuple[float, float, float, float]] = []

    def text(self, ratio: float | None, operands: list[Any]) -> None:
        # Bytes, not characters: two-byte fonts count double. Precise enough
        # to tell a footer from a page of text.
        strings = operands[0] if operands and isinstance(operands[0], list) else operands
        self.visible_text_chars += sum(len(x) for x in strings if isinstance(x, (bytes, str)))
        if ratio is not None:
            self.lowest_contrast = ratio if self.lowest_contrast is None else min(self.lowest_contrast, ratio)


def _scan_content(stream_owner: Any, resources: Any, reader: PdfReader, scan: _PageScan,
                  ctm: list[float], depth: int, seen: set[int]) -> None:
    try:
        stream = ContentStream(stream_owner, reader)
    except Exception:
        return
    # Fill rgb (None = unknown colour), fill colour-space components, fill
    # alpha, text render mode, and current transformation matrix.
    state: dict[str, Any] = {"rgb": (0.0, 0.0, 0.0), "space": 1, "alpha": 1.0, "mode": 0, "ctm": ctm}
    stack: list[dict[str, Any]] = []
    for operands, operator in stream.operations:
        op = operator.decode("latin-1") if isinstance(operator, bytes) else str(operator)
        try:
            if op == "q":
                stack.append(dict(state))
            elif op == "Q" and stack:
                state = stack.pop()
            elif op == "cm":
                state["ctm"] = _multiply([float(x) for x in operands[:6]], state["ctm"])
            elif op == "g":
                state["rgb"], state["space"] = _rgb_from_components([float(operands[0])]), 1
            elif op == "rg":
                state["rgb"], state["space"] = _rgb_from_components([float(x) for x in operands[:3]]), 3
            elif op == "k":
                state["rgb"], state["space"] = _rgb_from_components([float(x) for x in operands[:4]]), 4
            elif op == "cs":
                state["space"] = _colour_space_components(_name(operands[0]), resources)
                # Initial colour of every supported space is black.
                state["rgb"] = (0.0, 0.0, 0.0) if state["space"] else None
            elif op in {"sc", "scn"}:
                numbers = [float(x) for x in operands if not _name(x).startswith("/")]
                if state["space"] and len(numbers) == state["space"]:
                    state["rgb"] = _rgb_from_components(numbers)
                else:
                    state["rgb"] = None
            elif op == "gs":
                gstate = resources.get("/ExtGState").get_object().get(_name(operands[0])).get_object()
                if "/ca" in gstate:
                    state["alpha"] = float(gstate["/ca"])
            elif op == "Tr":
                state["mode"] = int(operands[0])
            elif op in _TEXT_SHOWING:
                # Modes 3 (invisible) and 7 (clip only) paint nothing; modes 1
                # and 5 stroke rather than fill, which this check does not model.
                if state["mode"] in {0, 2, 4, 6}:
                    rgb = state["rgb"]
                    scan.text(None if rgb is None else _contrast_against_white(rgb, state["alpha"]), operands)
                elif state["mode"] in {1, 5}:
                    scan.text(None, operands)
            elif op == "BI":
                scan.image_boxes.append(_unit_square_bbox(state["ctm"]))
            elif op == "Do":
                xobject = resources.get("/XObject").get_object().get(_name(operands[0]))
                key = getattr(xobject, "idnum", None)
                xobject = xobject.get_object()
                subtype = _name(xobject.get("/Subtype"))
                if subtype == "/Image":
                    scan.image_boxes.append(_unit_square_bbox(state["ctm"]))
                    continue
                if subtype != "/Form" or depth >= 8 or (key is not None and key in seen):
                    continue
                if key is not None:
                    seen.add(key)
                inner_resources = xobject.get("/Resources")
                inner_resources = inner_resources.get_object() if inner_resources is not None else resources
                matrix = [float(x) for x in xobject.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                _scan_content(xobject, inner_resources, reader, scan, _multiply(matrix, state["ctm"]), depth + 1, seen)
        except (TypeError, ValueError, IndexError, AttributeError, KeyError):
            continue


def _largest_image_coverage(boxes: list[tuple[float, float, float, float]], page_box: Any) -> float:
    """Largest fraction of the page area covered by any single image."""
    try:
        left, bottom, right, top = (float(x) for x in page_box)
    except Exception:
        return 0.0
    area = (right - left) * (top - bottom)
    if area <= 0:
        return 0.0
    best = 0.0
    for x0, y0, x1, y1 in boxes:
        width = max(0.0, min(x1, right) - max(x0, left))
        height = max(0.0, min(y1, top) - max(y0, bottom))
        best = max(best, width * height / area)
    return best


def _scan_pages(reader: PdfReader, facts: DocumentFacts) -> None:
    """Text colour and image placement, from content-stream operators.

    Contrast assumes a white page: this does not see the real background, so
    white text on a dark box is a false positive. Rendered analysis is a TODO.
    """
    worst: float | None = None
    for page in reader.pages:
        scan = _PageScan()
        try:
            resources = page.get("/Resources")
            resources = resources.get_object() if resources is not None else {}
            contents = page.get_contents()
            if contents is not None:
                _scan_content(contents, resources, reader, scan, [1, 0, 0, 1, 0, 0], 0, set())
        except Exception:
            pass
        facts.page_visible_text_chars.append(scan.visible_text_chars)
        facts.page_largest_image_coverage.append(_largest_image_coverage(scan.image_boxes, page.mediabox))
        if scan.lowest_contrast is not None:
            worst = scan.lowest_contrast if worst is None else min(worst, scan.lowest_contrast)
    facts.lowest_text_contrast = worst


def extract_facts(path: str | Path, password: str | None = None) -> DocumentFacts:
    source = Path(path)
    facts = DocumentFacts(path=source)
    try:
        reader = PdfReader(source, strict=False)
        facts.encrypted = reader.is_encrypted
        if reader.is_encrypted:
            if not password or not reader.decrypt(password):
                return facts
        facts.page_count = len(reader.pages)
        try:
            metadata = reader.metadata
            facts.title = _text(metadata.title) if metadata else None
        except Exception:
            facts.title = None
        catalog = reader.trailer["/Root"]
        facts.language = _text(catalog.get("/Lang"))
        tree = catalog.get("/StructTreeRoot")
        if tree is not None:
            try:
                tree_obj = tree.get_object()
            except Exception:
                tree_obj = None
            facts.tagged = hasattr(tree_obj, "get")
        if facts.tagged:
            rolemap_obj = tree_obj.get("/RoleMap", {})
            try:
                rolemap_obj = rolemap_obj.get_object()
            except Exception:
                pass
            rolemap = {str(k): v for k, v in rolemap_obj.items()} if hasattr(rolemap_obj, "items") else {}
            _walk_structure(tree, rolemap, facts.structure, set(), facts.table_header_presence, None, facts.table_cell_counts, facts.table_row_counts)
        for page in reader.pages:
            try:
                facts.page_text.append(page.extract_text() or "")
                facts.page_text_errors.append(False)
            except Exception:
                facts.page_text.append("")
                facts.page_text_errors.append(True)
            try:
                facts.page_image_counts.append(len(page.images))
                facts.page_image_errors.append(False)
            except Exception:
                facts.page_image_counts.append(0)
                facts.page_image_errors.append(True)
        _scan_pages(reader, facts)
    except Exception as exc:
        facts.parsable = False
        facts.parse_error = f"{type(exc).__name__}: {exc}"
    return facts
