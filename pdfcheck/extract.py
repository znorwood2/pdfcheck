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
        elif resolved == "/TH" and active_table is not None:
            table_headers[active_table] = True
    children = obj.get("/K", [])
    if not isinstance(children, list):
        children = [children]
    for child in children:
        _walk_structure(child, rolemap, output, seen, table_headers, active_table)


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


def _scan_text_contrast(stream_owner: Any, resources: Any, reader: PdfReader, depth: int, seen: set[int]) -> float | None:
    """Return the lowest contrast ratio of visible text against an assumed white page."""
    try:
        stream = ContentStream(stream_owner, reader)
    except Exception:
        return None
    worst: float | None = None
    # State: fill rgb (None = unknown colour), fill colour-space components,
    # fill alpha, text render mode.
    state: dict[str, Any] = {"rgb": (0.0, 0.0, 0.0), "space": 1, "alpha": 1.0, "mode": 0}
    stack: list[dict[str, Any]] = []
    for operands, operator in stream.operations:
        op = operator.decode("latin-1") if isinstance(operator, bytes) else str(operator)
        try:
            if op == "q":
                stack.append(dict(state))
            elif op == "Q" and stack:
                state = stack.pop()
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
                if state["mode"] in {0, 2, 4, 6} and state["rgb"] is not None:
                    ratio = _contrast_against_white(state["rgb"], state["alpha"])
                    worst = ratio if worst is None else min(worst, ratio)
            elif op == "Do" and depth < 8:
                xobject = resources.get("/XObject").get_object().get(_name(operands[0]))
                key = getattr(xobject, "idnum", None)
                xobject = xobject.get_object()
                if _name(xobject.get("/Subtype")) != "/Form" or (key is not None and key in seen):
                    continue
                if key is not None:
                    seen.add(key)
                inner_resources = xobject.get("/Resources")
                inner_resources = inner_resources.get_object() if inner_resources is not None else resources
                ratio = _scan_text_contrast(xobject, inner_resources, reader, depth + 1, seen)
                if ratio is not None:
                    worst = ratio if worst is None else min(worst, ratio)
        except (TypeError, ValueError, IndexError, AttributeError, KeyError):
            continue
    return worst


def _lowest_text_contrast(reader: PdfReader) -> float | None:
    """Lowest WCAG contrast of painted text, assuming a white background.

    This is an operator-level heuristic: it does not see the real background,
    so white text on a dark box is a false positive. Rendered analysis is a TODO.
    """
    worst: float | None = None
    for page in reader.pages:
        try:
            resources = page.get("/Resources")
            resources = resources.get_object() if resources is not None else {}
            contents = page.get_contents()
        except Exception:
            continue
        if contents is None:
            continue
        ratio = _scan_text_contrast(contents, resources, reader, 0, set())
        if ratio is not None:
            worst = ratio if worst is None else min(worst, ratio)
    return worst


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
            _walk_structure(tree, rolemap, facts.structure, set(), facts.table_header_presence)
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
        facts.lowest_text_contrast = _lowest_text_contrast(reader)
    except Exception as exc:
        facts.parsable = False
        facts.parse_error = f"{type(exc).__name__}: {exc}"
    return facts
