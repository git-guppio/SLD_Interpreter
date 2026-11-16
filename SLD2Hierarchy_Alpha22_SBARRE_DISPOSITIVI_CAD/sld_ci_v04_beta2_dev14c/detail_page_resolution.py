"""Resolve per-container detail-page context and transformer instances.

The resolver is intentionally evidence-driven and document-generic:
- cross-sheet CU references do not define page ownership;
- a unique local CU instance (or a dominant child-equipment CU hint) can define
  the page scope;
- apparent-power rating + nearby voltage-ratio evidence can infer a transformer
  instance when there is no explicit transformer INSTANCE/TAG on that page;
- the transformer role is inferred only when the voltage levels distinguish
  MV/LV or LV/LV;
- every inferred transformer keeps the source anchors and CU page context used.

No Ground Truth is consulted.
"""
from __future__ import annotations

from collections import Counter
from math import hypot
from typing import Any, Dict, List, Optional, Tuple


def _center(bbox: List[float] | Tuple[float, float, float, float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = [float(v) for v in bbox]
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _union_bbox(*boxes: List[float] | Tuple[float, float, float, float]) -> List[float]:
    vals = [[float(v) for v in b] for b in boxes if b]
    return [
        min(v[0] for v in vals),
        min(v[1] for v in vals),
        max(v[2] for v in vals),
        max(v[3] for v in vals),
    ]


def _page_cu_context(page: Dict[str, Any]) -> Dict[str, Any]:
    anchors = list(page.get("text_equipment_anchors", []) or [])

    local = [
        str((a.get("attributes", {}) or {}).get("instance_hint"))
        for a in anchors
        if a.get("equipment_type") == "CONVERSION_UNIT"
        and a.get("anchor_role") in {"INSTANCE", "TAG"}
        and (a.get("attributes", {}) or {}).get("instance_hint") is not None
    ]
    local_unique = sorted(set(local))
    if len(local_unique) == 1:
        return {
            "cu_instance_hint": local_unique[0],
            "source_status": "DETECTED",
            "basis": "UNIQUE_LOCAL_CU_INSTANCE",
            "support_count": len(local),
        }

    # Fallback: infer page scope from the dominant CU hint carried by local
    # target equipment tags (e.g. INV.x.y / SB.x.y.z).  Require strong
    # dominance so cross-sheet references cannot steal page ownership.
    child_hints: List[str] = []
    for a in anchors:
        attrs = a.get("attributes", {}) or {}
        hint = attrs.get("cu_instance_hint")
        if hint is not None and a.get("anchor_role") in {"INSTANCE", "TAG"}:
            child_hints.append(str(hint))
    if child_hints:
        counts = Counter(child_hints)
        winner, n = counts.most_common(1)[0]
        total = sum(counts.values())
        second = counts.most_common(2)[1][1] if len(counts) > 1 else 0
        if n >= 2 and n > second and n / total >= 0.70:
            return {
                "cu_instance_hint": winner,
                "source_status": "INFERRED",
                "basis": "DOMINANT_CHILD_EQUIPMENT_CU_HINT",
                "support_count": n,
                "total_child_hints": total,
            }

    return {
        "cu_instance_hint": None,
        "source_status": "UNRESOLVED",
        "basis": "NO_UNIQUE_PAGE_CU_CONTEXT",
        "support_count": 0,
    }


def _transformer_role(voltage_values_v: List[float]) -> Optional[str]:
    vals = [float(v) for v in voltage_values_v if v is not None and float(v) > 0]
    if len(vals) < 2:
        return None
    lo, hi = min(vals), max(vals)
    # Target distinction used by this project.  1 kV is the boundary between
    # LV and MV for the current hierarchy purpose.
    if lo < 1000.0 <= hi:
        return "MV_LV_TRANSFORMER"
    if hi < 1000.0 and abs(hi - lo) > 1e-6:
        return "LV_LV_TRANSFORMER"
    return None


def _pair_rating_and_ratio(page: Dict[str, Any]) -> List[Dict[str, Any]]:
    anchors = list(page.get("text_equipment_anchors", []) or [])
    ratings = [
        a for a in anchors
        if a.get("equipment_type") == "TRANSFORMER_CANDIDATE"
        and a.get("evidence_kind") == "APPARENT_POWER_RATING"
        and a.get("bbox")
    ]
    ratios = [
        a for a in anchors
        if a.get("equipment_type") == "TRANSFORMER_CANDIDATE"
        and a.get("evidence_kind") == "VOLTAGE_RATIO"
        and a.get("bbox")
    ]
    if not ratings or not ratios:
        return []

    diag = hypot(float(page.get("page_width_pt") or 1.0), float(page.get("page_height_pt") or 1.0))
    max_dist = max(30.0, diag * 0.045)

    pairs: List[Dict[str, Any]] = []
    used_ratio_ids = set()
    for rating in sorted(ratings, key=lambda a: (_center(a["bbox"])[0], _center(a["bbox"])[1])):
        rc = _center(rating["bbox"])
        candidates = []
        for ratio in ratios:
            if ratio.get("anchor_id") in used_ratio_ids:
                continue
            vc = _center(ratio["bbox"])
            d = hypot(rc[0] - vc[0], rc[1] - vc[1])
            # Prefer same-column semantic clusters.  This guards against pairing
            # a rating with a neighboring transformer's ratio on repeated layouts.
            dx = abs(rc[0] - vc[0])
            if d <= max_dist and dx <= max_dist * 0.60:
                candidates.append((d, dx, ratio))
        if not candidates:
            continue
        candidates.sort(key=lambda x: (x[0], x[1], x[2].get("anchor_id") or ""))
        d, _, ratio = candidates[0]
        used_ratio_ids.add(ratio.get("anchor_id"))
        pairs.append({
            "rating_anchor": rating,
            "voltage_ratio_anchor": ratio,
            "distance_pt": d,
            "bbox": _union_bbox(rating["bbox"], ratio["bbox"]),
        })
    return pairs


def resolve_detail_page_transformers(
    pages: List[Dict[str, Any]],
    accepted_equipment: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    accepted_equipment = list(accepted_equipment or [])
    entities: List[Dict[str, Any]] = []
    page_contexts: List[Dict[str, Any]] = []
    unresolved_clusters: List[Dict[str, Any]] = []

    accepted_transformer_pages = {
        int(o.get("page"))
        for e in accepted_equipment
        if e.get("equipment_type") in {"MV_LV_TRANSFORMER", "LV_LV_TRANSFORMER"}
        for o in (e.get("occurrences", []) or [])
        if o.get("page") is not None
    }

    for page in pages:
        ctx = _page_cu_context(page)
        page_contexts.append({"doc": page.get("doc"), "page": page.get("page"), **ctx})

        # Explicit target transformer INSTANCE/TAG evidence takes precedence.
        explicit = [
            a for a in (page.get("text_equipment_anchors", []) or [])
            if a.get("equipment_type") in {"MV_LV_TRANSFORMER", "LV_LV_TRANSFORMER"}
            and a.get("anchor_role") in {"INSTANCE", "TAG"}
        ]
        if explicit or int(page.get("page") or -1) in accepted_transformer_pages:
            continue

        pairs = _pair_rating_and_ratio(page)
        if not pairs:
            continue

        if ctx.get("cu_instance_hint") is None:
            for pair in pairs:
                unresolved_clusters.append({
                    "doc": page.get("doc"),
                    "page": page.get("page"),
                    "reason": "TRANSFORMER_SEMANTIC_CLUSTER_WITHOUT_CU_PAGE_CONTEXT",
                    "rating_anchor_id": pair["rating_anchor"].get("anchor_id"),
                    "voltage_ratio_anchor_id": pair["voltage_ratio_anchor"].get("anchor_id"),
                    "bbox": pair["bbox"],
                })
            continue

        resolved = []
        for pair in pairs:
            ratio = pair["voltage_ratio_anchor"]
            role = _transformer_role((ratio.get("attributes", {}) or {}).get("voltage_values_v", []) or [])
            if role is None:
                unresolved_clusters.append({
                    "doc": page.get("doc"),
                    "page": page.get("page"),
                    "reason": "TRANSFORMER_ROLE_UNRESOLVED_FROM_VOLTAGE_RATIO",
                    "rating_anchor_id": pair["rating_anchor"].get("anchor_id"),
                    "voltage_ratio_anchor_id": ratio.get("anchor_id"),
                    "bbox": pair["bbox"],
                })
                continue
            resolved.append((pair, role))

        # Stable local ordering provides identity when the source has no tag.
        resolved.sort(key=lambda pr: (_center(pr[0]["bbox"])[0], _center(pr[0]["bbox"])[1]))
        for ordinal, (pair, role) in enumerate(resolved, start=1):
            rating = pair["rating_anchor"]
            ratio = pair["voltage_ratio_anchor"]
            doc = page.get("doc")
            cu = str(ctx["cu_instance_hint"])
            entities.append({
                "equipment_id": f"{doc}::{role}::CU_{cu}_SEMTR_{ordinal}",
                "equipment_type": role,
                "doc": doc,
                "tag": None,
                "source_symbol_ids": [],
                "occurrences": [{
                    "page": page.get("page"),
                    "bbox": pair["bbox"],
                    "rating_bbox": rating.get("bbox"),
                    "voltage_ratio_bbox": ratio.get("bbox"),
                }],
                "anchor_ids": [rating.get("anchor_id"), ratio.get("anchor_id")],
                "acceptance_reason": "LOCAL_APPARENT_POWER_AND_VOLTAGE_RATIO_WITH_RESOLVED_CU_PAGE_CONTEXT",
                "confidence": 0.94 if ctx.get("source_status") == "DETECTED" else 0.90,
                "source_status": "INFERRED",
                "evidence_mode": "LOCAL_SEMANTIC_CLUSTER",
                "cu_instance_hint": cu,
                "membership_basis_hint": "DETAIL_PAGE_CU_CONTEXT",
                "semantic_evidence": {
                    "rating_text": rating.get("text"),
                    "rating_kva": (rating.get("attributes", {}) or {}).get("apparent_power_kva"),
                    "voltage_ratio_text": ratio.get("text"),
                    "voltage_values_v": (ratio.get("attributes", {}) or {}).get("voltage_values_v"),
                    "pair_distance_pt": pair.get("distance_pt"),
                    "page_context_basis": ctx.get("basis"),
                },
            })

    return {
        "page_contexts": page_contexts,
        "entities": entities,
        "unresolved_clusters": unresolved_clusters,
        "summary": {
            "resolved_transformer_count": len(entities),
            "mv_lv_transformer_count": sum(e.get("equipment_type") == "MV_LV_TRANSFORMER" for e in entities),
            "lv_lv_transformer_count": sum(e.get("equipment_type") == "LV_LV_TRANSFORMER" for e in entities),
            "unresolved_cluster_count": len(unresolved_clusters),
        },
        "policy": "SEMANTIC_CLUSTER_INFERENCE_REQUIRES_RATING_PLUS_VOLTAGE_RATIO_AND_RESOLVED_PAGE_CU_CONTEXT",
    }
