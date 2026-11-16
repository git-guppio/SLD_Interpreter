"""Structured schedule evidence extracted from positioned PDF text.

Schedules are evidence, not equipment inventories by themselves.  Dev9 adds a
conservative positioned parser for repeated BLOCK SCHEDULE tables.  A row is
accepted only when multiple columns align on the same baseline: block id,
wiring-pattern token, combiner count, module manufacturer and detail-sheet
reference.  This avoids manufacturing rows from text extraction order.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Tuple

MV_SCHEDULE_PATTERN = re.compile(r"\b(MV[-_ ]\d{1,3})\s+CIRCUIT\s+SCHEDULE\b", re.I)


def _center(item: Any) -> Tuple[float, float]:
    b = getattr(item, "bbox", (0, 0, 0, 0))
    return ((float(b[0]) + float(b[2])) / 2.0, (float(b[1]) + float(b[3])) / 2.0)


def _norm(text: Any) -> str:
    return " ".join(str(text or "").strip().upper().split())


def extract_schedule_evidence(items: Iterable[Any]) -> List[Dict[str, Any]]:
    """Existing MV schedule-header evidence, with normalized feeder labels."""
    result: List[Dict[str, Any]] = []
    for item in items:
        for m in MV_SCHEDULE_PATTERN.finditer(str(getattr(item, "text", ""))):
            raw = m.group(1).upper().replace("_", "-").replace(" ", "-")
            mm = re.search(r"MV-(\d{1,3})", raw)
            feeder = f"MV-{int(mm.group(1)):02d}" if mm else raw
            result.append({
                "schedule_id": f"{item.doc}_P{item.page}_{len(result)+1}_SCHEDULE",
                "doc": item.doc,
                "page": item.page,
                "bbox": list(item.bbox),
                "feeder_label": feeder,
                "source": item.source,
                "confidence": item.confidence,
                "status": "UNRESOLVED_TABLE_ROWS",
                "rows": [],
                "reason": "HEADER_ONLY_NOT_EQUIPMENT_OR_RELATION",
            })
    return result


def _block_header_columns(items: List[Any]) -> List[Tuple[float, float]]:
    """Return x/y anchors of BLOCK # columns that belong to BLOCK SCHEDULE tables."""
    schedule_titles = [it for it in items if "BLOCK SCHEDULE" in _norm(getattr(it, "text", ""))]
    if not schedule_titles:
        return []

    headers: List[Tuple[float, float]] = []
    for it in items:
        t = _norm(getattr(it, "text", ""))
        x, y = _center(it)
        if t == "BLOCK #":
            headers.append((x, y))
        elif t == "BLOCK":
            hashes = [
                z for z in items
                if str(getattr(z, "text", "")).strip() == "#"
                and abs(_center(z)[0] - x) < 25.0
                and 0.0 < (_center(z)[1] - y) < 35.0
            ]
            if hashes:
                headers.append((x, (y + _center(hashes[0])[1]) / 2.0))

    # A generic page can mention BLOCK elsewhere.  Retain only headers spatially
    # close to a BLOCK SCHEDULE title and below it.
    valid: List[Tuple[float, float]] = []
    for hx, hy in headers:
        ok = False
        for title in schedule_titles:
            tx, ty = _center(title)
            if hy < ty - 10.0:
                continue
            dy = max(0.0, hy - ty)
            if math.hypot(hx - tx, dy) < 180.0:
                ok = True
                break
        if ok and (hx, hy) not in valid:
            valid.append((hx, hy))
    return valid


def extract_block_schedule_rows(items: Iterable[Any]) -> List[Dict[str, Any]]:
    """Parse positioned BLOCK SCHEDULE rows conservatively.

    The parser does not assume specific manufacturers, block counts or Roadrunner
    values.  It relies on repeated table-column geometry and requires five
    independent row fields.  This makes the resulting cardinality evidence much
    stronger than plain text-order parsing.
    """
    items = list(items)
    headers = _block_header_columns(items)
    if not headers:
        return []

    rows: Dict[str, Dict[str, Any]] = {}
    for hx, hy in headers:
        for item in items:
            raw = str(getattr(item, "text", "")).strip()
            x, y = _center(item)
            if not re.fullmatch(r"\d{1,4}", raw):
                continue
            if abs(x - hx) > 26.0 or y < hy + 18.0:
                continue

            aligned = []
            for z in items:
                zx, zy = _center(z)
                if abs(zy - y) <= 3.6:
                    aligned.append((zx, str(getattr(z, "text", "")).strip(), z))

            wiring = next((
                t for zx, t, _ in aligned
                if hx + 30.0 < zx < hx + 100.0
                and re.fullmatch(r"[A-Z0-9]{4,12}", t, re.I)
                and re.search(r"[A-Z]", t, re.I)
                and re.search(r"\d", t)
            ), None)
            combiner = next((
                int(t) for zx, t, _ in aligned
                if hx + 95.0 < zx < hx + 155.0
                and re.fullmatch(r"\d{1,2}", t)
                and 1 <= int(t) <= 50
            ), None)
            manufacturer = next((
                t for zx, t, _ in aligned
                if hx + 155.0 < zx < hx + 235.0
                and re.fullmatch(r"[A-Z][A-Z0-9&.\-/]{2,}", t, re.I)
            ), None)
            detail_sheet = next((
                t.upper() for zx, t, _ in aligned
                if hx + 220.0 < zx < hx + 310.0
                and re.fullmatch(r"[A-Z]-\d{2,4}", t, re.I)
            ), None)

            # Require all columns; otherwise keep the table unresolved rather
            # than infer a row from a lone integer.
            if not (wiring and combiner is not None and manufacturer and detail_sheet):
                continue

            block_id = str(int(raw))
            existing = rows.get(block_id)
            record = {
                "block_instance_key": block_id,
                "wiring_pattern": wiring.upper(),
                "combiner_box_count": int(combiner),
                "module_manufacturer": manufacturer.upper(),
                "detail_sheet": detail_sheet,
                "doc": getattr(item, "doc", None),
                "page": getattr(item, "page", None),
                "bbox": list(getattr(item, "bbox", (0, 0, 0, 0))),
                "source": getattr(item, "source", None),
                "confidence": getattr(item, "confidence", None),
                "source_status": "DETECTED",
                "evidence_kind": "POSITIONED_BLOCK_SCHEDULE_ROW",
            }
            if existing and any(existing.get(k) != record.get(k) for k in (
                "wiring_pattern", "combiner_box_count", "module_manufacturer", "detail_sheet"
            )):
                # Contradictory duplicate rows are not silently overwritten.
                existing.setdefault("conflicts", []).append(record)
                existing["status"] = "CONFLICTING_SOURCE_ROWS"
            else:
                rows[block_id] = record

    return [rows[k] for k in sorted(rows, key=lambda v: (not v.isdigit(), int(v) if v.isdigit() else v))]


def _canonical_mv_label(raw: str) -> str:
    m = re.search(r"MV\s*[-_ ]?\s*(\d{1,3})", str(raw or ""), re.I)
    if not m:
        return _norm(raw).replace("_", "-")
    return f"MV-{int(m.group(1)):02d}"


def extract_mv_circuit_schedule_rows(items: Iterable[Any]) -> List[Dict[str, Any]]:
    """Parse explicit ``MV-xx CIRCUIT SCHEDULE`` membership rows.

    The relation is source-explicit: a block row is accepted only when the page
    contains an MV circuit-schedule title and the same five positioned columns
    used by the generic block-schedule parser can be resolved on one baseline.
    Nothing is inferred from row order alone.
    """
    items = list(items)
    schedule_titles = []
    for it in items:
        t = _norm(getattr(it, "text", ""))
        m = MV_SCHEDULE_PATTERN.search(t)
        if m:
            schedule_titles.append((it, _canonical_mv_label(m.group(1))))
    if not schedule_titles:
        return []

    # Locate BLOCK/# header(s) close to and below each circuit-schedule title.
    headers: List[Tuple[float, float, str, Any]] = []
    for title_item, feeder in schedule_titles:
        tx, ty = _center(title_item)
        candidates: List[Tuple[float, float, Any]] = []
        for it in items:
            t = _norm(getattr(it, "text", ""))
            x, y = _center(it)
            if y < ty - 8.0 or y > ty + 150.0:
                continue
            if t == "BLOCK #":
                candidates.append((x, y, it))
            elif t == "BLOCK":
                hashes = [
                    z for z in items
                    if str(getattr(z, "text", "")).strip() == "#"
                    and abs(_center(z)[0] - x) < 25.0
                    and 0.0 < (_center(z)[1] - y) < 35.0
                ]
                if hashes:
                    candidates.append((x, (y + _center(hashes[0])[1]) / 2.0, it))
        if candidates:
            candidates.sort(key=lambda r: math.hypot(r[0] - tx, max(0.0, r[1] - ty)))
            hx, hy, hit = candidates[0]
            headers.append((hx, hy, feeder, hit))

    out: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for hx, hy, feeder, _ in headers:
        for item in items:
            raw = str(getattr(item, "text", "")).strip()
            x, y = _center(item)
            if not re.fullmatch(r"\d{1,4}", raw):
                continue
            if abs(x - hx) > 28.0 or y < hy + 14.0:
                continue

            aligned = []
            for z in items:
                zx, zy = _center(z)
                if abs(zy - y) <= 3.8:
                    aligned.append((zx, str(getattr(z, "text", "")).strip(), z))

            wiring = next((
                t for zx, t, _ in aligned
                if hx + 28.0 < zx < hx + 105.0
                and re.fullmatch(r"[A-Z0-9]{4,12}", t, re.I)
                and re.search(r"[A-Z]", t, re.I)
                and re.search(r"\d", t)
            ), None)
            combiner = next((
                int(t) for zx, t, _ in aligned
                if hx + 90.0 < zx < hx + 160.0
                and re.fullmatch(r"\d{1,2}", t)
                and 1 <= int(t) <= 50
            ), None)
            manufacturer = next((
                t for zx, t, _ in aligned
                if hx + 150.0 < zx < hx + 245.0
                and re.fullmatch(r"[A-Z][A-Z0-9&.\-/]{2,}", t, re.I)
            ), None)
            detail_sheet = next((
                t.upper() for zx, t, _ in aligned
                if hx + 210.0 < zx < hx + 330.0
                and re.fullmatch(r"[A-Z]-\d{2,4}", t, re.I)
            ), None)
            if not (wiring and combiner is not None and manufacturer and detail_sheet):
                continue

            block_id = str(int(raw))
            key = (feeder, block_id)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "mv_line_instance_key": feeder,
                "block_instance_key": block_id,
                "wiring_pattern": wiring.upper(),
                "combiner_box_count": int(combiner),
                "module_manufacturer": manufacturer.upper(),
                "detail_sheet": detail_sheet,
                "doc": getattr(item, "doc", None),
                "page": getattr(item, "page", None),
                "bbox": list(getattr(item, "bbox", (0, 0, 0, 0))),
                "source": getattr(item, "source", None),
                "confidence": getattr(item, "confidence", None),
                "source_status": "DETECTED",
                "evidence_kind": "EXPLICIT_MV_CIRCUIT_SCHEDULE_MEMBERSHIP",
            })

    return sorted(out, key=lambda r: (
        int(re.search(r"(\d+)$", r["mv_line_instance_key"]).group(1))
        if re.search(r"(\d+)$", r["mv_line_instance_key"]) else 10**9,
        int(r["block_instance_key"]) if r["block_instance_key"].isdigit() else 10**9,
        r["block_instance_key"],
    ))
