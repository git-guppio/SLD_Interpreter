"""Apply validated operator feedback to unresolved candidate groups.

Visual selection is interpreted against existing candidate groups first.  If a
bbox overlaps no candidate group, the event is preserved as DETECTION_FAILURE
rather than silently creating geometry.
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple

from .operator_interaction import validate_feedback_batch


def _intersection_over_min(a, b) -> float:
    x0 = max(float(a[0]), float(b[0])); y0 = max(float(a[1]), float(b[1]))
    x1 = min(float(a[2]), float(b[2])); y1 = min(float(a[3]), float(b[3]))
    inter = max(0.0, x1-x0) * max(0.0, y1-y0)
    aa = max(0.0, float(a[2])-float(a[0])) * max(0.0, float(a[3])-float(a[1]))
    bb = max(0.0, float(b[2])-float(b[0])) * max(0.0, float(b[3])-float(b[1]))
    return inter / max(min(aa, bb), 1e-9)


def apply_operator_feedback(
    groups: List[Dict[str, Any]],
    accepted_equipment: List[Dict[str, Any]],
    feedback_records: Iterable[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    records = validate_feedback_batch(feedback_records)
    equipment = [dict(e) for e in accepted_equipment]
    diagnostics: List[Dict[str, Any]] = []
    group_map = {g.get("group_id"): g for g in groups}
    existing_group_ids = {e.get("group_id") or e.get("equipment_id", "").removesuffix("_EQ") for e in equipment}

    for fb in records:
        if fb.get("option") != "SELECT_DEVICE":
            if fb.get("option") in {"NOT_REPRESENTED_IN_SLD", "UNABLE_TO_IDENTIFY"}:
                diagnostics.append({
                    "request_id": fb.get("request_id"),
                    "status": fb.get("option"),
                    "source_status": "OPERATOR_PROVIDED",
                })
            continue

        gid = fb.get("group_id")
        group = group_map.get(gid) if gid else None
        if group is None and fb.get("bbox") is not None:
            candidates = []
            for g in groups:
                if g.get("doc") != fb.get("doc") or g.get("page") != fb.get("page"):
                    continue
                boxes = [m.get("bbox") for m in g.get("members", []) if m.get("bbox")]
                if not boxes:
                    continue
                gb = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
                ov = _intersection_over_min(fb["bbox"], gb)
                if ov > 0:
                    candidates.append((ov, g))
            candidates.sort(key=lambda x: (-x[0], x[1].get("group_id", "")))
            if candidates and candidates[0][0] >= 0.35:
                group = candidates[0][1]
                gid = group.get("group_id")

        if group is None:
            diagnostics.append({
                "request_id": fb.get("request_id"),
                "status": "DETECTION_FAILURE",
                "reason": "OPERATOR_SELECTION_OVERLAPS_NO_EXISTING_CANDIDATE",
                "source_status": "OPERATOR_PROVIDED",
                "doc": fb.get("doc"),
                "page": fb.get("page"),
                "bbox": fb.get("bbox"),
                "device_type": fb.get("device_type"),
            })
            continue

        if gid in existing_group_ids:
            diagnostics.append({
                "request_id": fb.get("request_id"),
                "status": "ALREADY_AUTOMATICALLY_ACCEPTED",
                "group_id": gid,
                "source_status": "OPERATOR_PROVIDED",
            })
            continue

        members = group.get("members", [])
        occurrences = [
            {"page": group.get("page"), "bbox": m.get("bbox"), "symbol_id": m.get("symbol_id")}
            for m in members if m.get("bbox")
        ]
        eq = {
            "equipment_id": gid + "_EQ_OP",
            "group_id": gid,
            "equipment_type": fb.get("device_type"),
            "doc": group.get("doc"),
            "tag": fb.get("tag"),
            "source_symbol_ids": [m.get("symbol_id") for m in members if m.get("symbol_id")],
            "occurrences": occurrences,
            "anchor_ids": [a.get("anchor_id") for a in group.get("anchors", []) if a.get("anchor_id")],
            "acceptance_reason": "OPERATOR_VISUAL_SELECTION",
            "confidence": None,
            "source_status": "OPERATOR_PROVIDED",
            "operator_request_id": fb.get("request_id"),
            "operator_context": fb.get("context", {}),
        }
        equipment.append(eq)
        existing_group_ids.add(gid)
        diagnostics.append({
            "request_id": fb.get("request_id"),
            "status": "CLASSIFICATION_FAILURE_RESOLVED_BY_OPERATOR",
            "group_id": gid,
            "equipment_id": eq["equipment_id"],
            "device_type": eq["equipment_type"],
            "source_status": "OPERATOR_PROVIDED",
        })

    return equipment, diagnostics
