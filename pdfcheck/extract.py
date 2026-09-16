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


def _has_probable_low_contrast_text(reader: PdfReader) -> bool:
    """Conservative operator-level heuristic; visual background analysis is a TODO."""
    for page in reader.pages:
        try:
            stream = ContentStream(page.get_contents(), reader)
        except Exception:
            continue
        fill_luminance = 0.0
        stack: list[float] = []
        for operands, operator in stream.operations:
            op = operator.decode("latin-1") if isinstance(operator, bytes) else str(operator)
            try:
                if op == "g":
                    fill_luminance = float(operands[0])
                elif op == "rg":
                    r, g, b = map(float, operands[:3])
                    fill_luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                elif op == "k":
                    c, m, y, k = map(float, operands[:4])
                    r, g, b = 1 - min(1, c + k), 1 - min(1, m + k), 1 - min(1, y + k)
                    fill_luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                elif op == "q":
                    stack.append(fill_luminance)
                elif op == "Q" and stack:
                    fill_luminance = stack.pop()
                elif op in {"Tj", "TJ", "'", '"'} and fill_luminance >= 0.94:
                    return True
            except (TypeError, ValueError, IndexError):
                continue
    return False


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
        facts.probable_low_contrast_text = _has_probable_low_contrast_text(reader)
    except Exception as exc:
        facts.parsable = False
        facts.parse_error = f"{type(exc).__name__}: {exc}"
    return facts
