from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pymupdf as fitz

from .config import GeometryThresholds
from .models import SymbolCandidate, TextEquipmentAnchor


def _bbox_distance(a, b) -> float:
    dx = max(0.0, max(a[0] - b[2], b[0] - a[2]))
    dy = max(0.0, max(a[1] - b[3], b[1] - a[3]))
    return math.hypot(dx, dy)


def _center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _dims(b):
    w = abs(b[2] - b[0])
    h = abs(b[3] - b[1])
    return (min(w, h), max(w, h))


def _near_black(color: Any, max_channel: float) -> bool:
    if color is None:
        return False
    try:
        return max(float(v) for v in color[:3]) <= max_channel
    except Exception:
        return False


def _is_closed_rect_drawing(d: Dict[str, Any]) -> bool:
    items = [it for it in d.get("items", []) if it]
    if any(it[0] == "re" for it in items):
        return True

    r = d.get("rect")
    if r is None:
        return False

    x0, y0, x1, y1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
    tol = max(0.8, min(abs(x1-x0), abs(y1-y0)) * 0.08)

    top = bottom = left = right = False
    for it in items:
        if it[0] != "l":
            continue
        a, b = it[1], it[2]
        ax, ay, bx, by = float(a.x), float(a.y), float(b.x), float(b.y)

        if abs(ay - by) <= tol:
            yy = (ay + by) / 2.0
            lo, hi = sorted((ax, bx))
            if abs(yy - y0) <= tol and lo <= x0 + tol and hi >= x1 - tol:
                top = True
            if abs(yy - y1) <= tol and lo <= x0 + tol and hi >= x1 - tol:
                bottom = True

        if abs(ax - bx) <= tol:
            xx = (ax + bx) / 2.0
            lo, hi = sorted((ay, by))
            if abs(xx - x0) <= tol and lo <= y0 + tol and hi >= y1 - tol:
                left = True
            if abs(xx - x1) <= tol and lo <= y0 + tol and hi >= y1 - tol:
                right = True

    return top and bottom and left and right


def _has_diagonal_near_bbox(
    drawings: Sequence[Dict[str, Any]],
    bbox: Tuple[float, float, float, float],
) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1-x0, y1-y0
    pad = max(1.0, min(w, h) * 0.15)

    for d in drawings:
        for it in d.get("items", []):
            if not it or it[0] != "l":
                continue
            a, b = it[1], it[2]
            ax, ay, bx, by = float(a.x), float(a.y), float(b.x), float(b.y)

            if not (
                x0-pad <= ax <= x1+pad and
                y0-pad <= ay <= y1+pad and
                x0-pad <= bx <= x1+pad and
                y0-pad <= by <= y1+pad
            ):
                continue

            dx, dy = abs(bx-ax), abs(by-ay)
            if dx >= 0.35*w and dy >= 0.35*h:
                return True
    return False


def find_text_guided_ci_scale_references(
    page: fitz.Page,
    anchors: List[TextEquipmentAnchor],
    geom: GeometryThresholds,
) -> List[Dict[str, Any]]:
    """
    Use explicit CENTRAL_INVERTER source text as a semantic anchor, then find
    the nearest plausible enclosure. This is NOT a hierarchy inference.

    The selected enclosure provides the document/page-relative symbol scale.
    """
    drawings = page.get_drawings()
    min_dim = min(float(page.mediabox.width), float(page.mediabox.height))
    search_radius = max(
        geom.ci_scale_seed_search_radius_min_pt,
        min_dim * geom.ci_scale_seed_search_radius_ratio,
    )

    refs: List[Dict[str, Any]] = []

    for anchor in anchors:
        if anchor.equipment_type != "CENTRAL_INVERTER":
            continue

        candidates = []

        for d_idx, d in enumerate(drawings):
            if not _near_black(d.get("color"), geom.near_black_max_channel):
                continue

            r = d.get("rect")
            if r is None:
                continue

            bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
            short_side, long_side = _dims(bbox)

            if short_side < geom.ci_scale_seed_min_side_pt:
                continue
            if long_side > geom.ci_scale_seed_max_side_pt:
                continue
            if not _is_closed_rect_drawing(d):
                continue

            distance = _bbox_distance(anchor.bbox, bbox)
            if distance > search_radius:
                continue

            aspect = long_side / max(short_side, 1e-9)
            if aspect > 4.0:
                continue

            has_diag = _has_diagonal_near_bbox(drawings, bbox)

            # Prefer converter-like enclosure, then proximity.
            score = (
                (1.0 if has_diag else 0.0),
                -distance,
                short_side,
            )
            candidates.append(
                (score, d_idx, bbox, short_side, long_side, distance, has_diag)
            )

        if not candidates:
            continue

        candidates.sort(reverse=True)
        _, d_idx, bbox, short_side, long_side, distance, has_diag = candidates[0]

        refs.append({
            "reference_id": f"{anchor.anchor_id}_SCALE_REF",
            "equipment_type": "CENTRAL_INVERTER",
            "anchor_id": anchor.anchor_id,
            "tag": anchor.tag,
            "bbox": [round(v, 3) for v in bbox],
            "center": [round(v, 3) for v in _center(bbox)],
            "short_side_pt": round(short_side, 3),
            "long_side_pt": round(long_side, 3),
            "aspect_ratio": round(long_side / max(short_side, 1e-9), 4),
            "text_to_symbol_distance_pt": round(distance, 3),
            "has_internal_diagonal": bool(has_diag),
            "drawing_index": int(d_idx),
            "source": "TEXT_GUIDED_VECTOR_SCALE_REFERENCE",
        })

    return refs


def apply_ci_scale_coherence(
    symbol_candidates: List[SymbolCandidate],
    scale_references: List[Dict[str, Any]],
    page_no: int,
    doc_id: str,
    geom: GeometryThresholds,
) -> Dict[str, Any]:
    """
    Apply engineer-supplied domain rule:
    within the plant, the same equipment family uses the same symbol scale.

    Rotation is normalized via short/long side dimensions.

    A geometry-only inverter candidate that is incompatible with the available
    inverter scale reference is demoted to an explicit scale-outlier class.
    """
    refs = [
        r for r in scale_references
        if r["equipment_type"] == "CENTRAL_INVERTER"
    ]

    # Keep evidence explicit when no reference exists.
    if not refs:
        for s in symbol_candidates:
            if s.candidate_type == "CENTRAL_INVERTER_CANDIDATE":
                s.evidence["scale_status"] = "UNRESOLVED_NO_REFERENCE"
        return {
            "reference_count": 0,
            "scale_outlier_count": 0,
            "scale_consistent_count": 0,
            "text_guided_ci_candidates_added": 0,
            "references": [],
        }

    # Beta1 selects the nearest page-local reference for each candidate.
    # Cross-page scale transfer is deliberately unresolved without family identity.

    scale_outliers = 0
    scale_consistent = 0

    for s in symbol_candidates:
        if s.candidate_type != "CENTRAL_INVERTER_CANDIDATE":
            continue

        ref = min(refs, key=lambda r: (_bbox_distance(s.bbox, r["bbox"]), r["reference_id"]))
        ref_short = float(ref["short_side_pt"])
        ref_long = float(ref["long_side_pt"])
        short_side, long_side = _dims(s.bbox)
        short_ratio = short_side / max(ref_short, 1e-9)
        long_ratio = long_side / max(ref_long, 1e-9)

        consistent = (
            geom.ci_scale_consistent_ratio_min
            <= short_ratio
            <= geom.ci_scale_consistent_ratio_max
            and
            geom.ci_scale_consistent_ratio_min
            <= long_ratio
            <= geom.ci_scale_consistent_ratio_max
        )

        s.evidence["scale_reference_id"] = ref["reference_id"]
        s.evidence["scale_short_ratio"] = round(short_ratio, 4)
        s.evidence["scale_long_ratio"] = round(long_ratio, 4)

        if consistent:
            s.evidence["scale_status"] = "CONSISTENT"
            scale_consistent += 1
        else:
            s.evidence["scale_status"] = "OUTLIER"
            s.evidence["original_candidate_type"] = s.candidate_type
            s.candidate_type = "REJECTED_CENTRAL_INVERTER_SCALE_OUTLIER"
            scale_outliers += 1

    # Add one text-guided inverter candidate at the reference geometry.
    # It is still a candidate, not an accepted equipment entity.
    added = 0
    for ref_index, ref in enumerate(refs, 1):
        guided = SymbolCandidate(
            symbol_id=f"{doc_id}_P{page_no:03d}_TXTGUIDED_INV_{ref_index:04d}",
            candidate_type="CENTRAL_INVERTER",
            bbox=tuple(ref["bbox"]),
            center=tuple(ref["center"]),
            page=page_no,
            doc=doc_id,
            confidence=0.96,
            evidence_state="FUSED",
            geometry_kind="TEXT_GUIDED_VECTOR_ENCLOSURE",
            text_anchor_id=ref["anchor_id"],
            tag=ref["tag"],
            terminals=[],
            evidence={
                "scale_status": "REFERENCE",
                "scale_reference_id": ref["reference_id"],
                "source": ref["source"],
                "has_internal_diagonal": ref["has_internal_diagonal"],
                "text_to_symbol_distance_pt": ref["text_to_symbol_distance_pt"],
            },
            accepted_entity=False,
        )
    
        # Avoid adding duplicate text-guided candidate if function is rerun.
        if not any(s.symbol_id == guided.symbol_id for s in symbol_candidates):
            symbol_candidates.append(guided)
            added += 1
    

    return {
        "reference_count": len(refs),
        "scale_outlier_count": scale_outliers,
        "scale_consistent_count": scale_consistent,
        "text_guided_ci_candidates_added": added,
        "references": refs,
    }
