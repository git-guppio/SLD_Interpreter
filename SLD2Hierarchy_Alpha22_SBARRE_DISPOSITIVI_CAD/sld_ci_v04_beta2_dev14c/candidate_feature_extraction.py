"""Minimum evidence profiles for target-hierarchy classification.

This module deliberately does *not* classify equipment.  It converts the
existing page/group evidence into a stable, auditable feature contract that
later classifiers and human-in-the-loop resolution can consume.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Tuple


def _dims(bbox: Iterable[float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = [float(v) for v in bbox]
    return max(0.0, x1 - x0), max(0.0, y1 - y0)


def _centre(bbox: Iterable[float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = [float(v) for v in bbox]
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def _q(value: float, step: float) -> int:
    if step <= 0:
        return 0
    return int(round(value / step))


def _morph_signature(profile: Dict[str, Any]) -> Tuple[Any, ...]:
    g = profile["geometry"]
    t = profile["topology"]
    # Coarse, scale-normalised bins: enough to group repeated morphology,
    # deliberately insufficient to assign an electrical equipment class.
    return (
        profile["candidate_type"],
        g.get("geometry_kind"),
        _q(g.get("normalized_width") or 0.0, 0.0015),
        _q(g.get("normalized_height") or 0.0, 0.0015),
        _q(g.get("aspect_ratio") or 0.0, 0.15),
        _q(g.get("circle_size_ratio") or 0.0, 0.08),
        _q(g.get("circle_distance_normalized") or 0.0, 0.0015),
        t.get("terminal_count"),
    )


def _group_bbox(members: List[Dict[str, Any]]) -> List[float]:
    boxes = [m["bbox"] for m in members if m.get("bbox")]
    if not boxes:
        return [0.0, 0.0, 0.0, 0.0]
    return [
        min(float(b[0]) for b in boxes),
        min(float(b[1]) for b in boxes),
        max(float(b[2]) for b in boxes),
        max(float(b[3]) for b in boxes),
    ]


def _primary_member(members: List[Dict[str, Any]]) -> Dict[str, Any]:
    geometry = [m for m in members if m.get("evidence_state") != "TEXT_ONLY"]
    pool = geometry or members
    return sorted(pool, key=lambda m: (-float(m.get("confidence", 0.0)), m.get("symbol_id", "")))[0]


def extract_candidate_features(
    pages: List[Dict[str, Any]],
    groups: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build the Minimum Feature Set without assigning equipment classes."""
    page_map = {(p.get("doc"), p.get("page")): p for p in pages}
    profiles: List[Dict[str, Any]] = []

    for group in groups:
        members = list(group.get("members", []))
        if not members:
            continue
        primary = _primary_member(members)
        page = page_map.get((group.get("doc"), group.get("page")), {})
        page_w = float(page.get("page_width_pt") or 0.0)
        page_h = float(page.get("page_height_pt") or 0.0)
        bbox = _group_bbox(members)
        width, height = _dims(bbox)
        cx, cy = _centre(bbox)

        terminals = []
        for m in members:
            for term in m.get("terminals", []) or []:
                item = dict(term)
                item["source_symbol_id"] = m.get("symbol_id")
                terminals.append(item)
        # terminal IDs are already stable; dedupe without losing provenance
        by_tid = {t.get("terminal_id"): t for t in terminals if t.get("terminal_id")}
        terminals = [by_tid[k] for k in sorted(by_tid)]
        graph_nodes = sorted({t.get("graph_node_id") for t in terminals if t.get("graph_node_id") is not None})

        anchors = list(group.get("anchors", []))
        by_role: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for a in anchors:
            by_role[a.get("anchor_role") or "UNKNOWN"].append(a)

        ev = primary.get("evidence", {}) or {}
        cdist = ev.get("circle_center_distance_pt")
        profile = {
            "group_id": group.get("group_id"),
            "candidate_id": primary.get("symbol_id"),
            "candidate_type": primary.get("candidate_type"),
            "document": group.get("doc"),
            "page": group.get("page"),
            "scope_status": group.get("scope_status"),
            "geometry": {
                "bbox": bbox,
                "width_pt": round(width, 4),
                "height_pt": round(height, 4),
                "aspect_ratio": round(width / height, 5) if height else None,
                "normalized_width": round(width / page_w, 7) if page_w else None,
                "normalized_height": round(height / page_h, 7) if page_h else None,
                "center_x_norm": round(cx / page_w, 7) if page_w else None,
                "center_y_norm": round(cy / page_h, 7) if page_h else None,
                "geometry_kind": primary.get("geometry_kind"),
                "circle_size_ratio": ev.get("circle_size_ratio"),
                "circle_distance_pt": cdist,
                "circle_distance_normalized": round(float(cdist) / min(page_w, page_h), 7)
                    if cdist is not None and min(page_w, page_h) > 0 else None,
                "consolidated_candidate_count": ev.get("consolidated_candidate_count", 1),
                "consolidated_candidate_ids": ev.get("consolidated_candidate_ids", []),
            },
            "topology": {
                "terminal_count": len(terminals),
                "terminal_ids": [t.get("terminal_id") for t in terminals],
                "graph_node_ids": graph_nodes,
                "graph_node_degrees": [
                    t.get("evidence", {}).get("graph_node_degree") for t in terminals
                    if t.get("evidence", {}).get("graph_node_degree") is not None
                ],
                "trace_relation_count": 0,
                "connected_candidate_ids": [],
                "parent_context": None,
                "electrical_position": None,
            },
            "local_semantics": {
                "instance_anchors": [a.get("anchor_id") for a in by_role.get("INSTANCE", [])],
                "tag_anchors": [a.get("anchor_id") for a in by_role.get("TAG", [])],
                "family_anchors": [a.get("anchor_id") for a in by_role.get("FAMILY", [])],
                "cardinality_anchors": [a.get("anchor_id") for a in by_role.get("CARDINALITY", [])],
                "rating_anchors": [a.get("anchor_id") for a in by_role.get("RATING", [])],
                "ratings": [
                    {
                        "anchor_id": a.get("anchor_id"),
                        "text": a.get("text"),
                        "apparent_power_value": (a.get("attributes") or {}).get("apparent_power_value"),
                        "apparent_power_unit": (a.get("attributes") or {}).get("apparent_power_unit"),
                        "apparent_power_kva": (a.get("attributes") or {}).get("apparent_power_kva"),
                    }
                    for a in by_role.get("RATING", [])
                ],
                "equipment_types": sorted({a.get("equipment_type") for a in anchors if a.get("equipment_type")}),
                "tags": sorted({a.get("tag") for a in anchors if a.get("tag")}),
                "relevant_text": [a.get("text") for a in anchors if a.get("text")],
                "direct_semantic_binding": any(
                    m.get("evidence_state") == "FUSED" and m.get("text_anchor_id")
                    for m in members
                ),
            },
            "document_context": {
                "page_type": page.get("page_type"),
                "page_width_pt": page_w or None,
                "page_height_pt": page_h or None,
                "family_anchor_counts_page": dict(Counter(
                    a.get("equipment_type") for a in page.get("text_equipment_anchors", [])
                    if a.get("anchor_role") == "FAMILY" and a.get("equipment_type")
                )),
            },
            "repetition": {
                "morph_family_id": None,
                "family_size": 1,
                "same_page_family_size": 1,
            },
            "provenance": {
                "source_symbol_ids": [m.get("symbol_id") for m in members],
                "anchor_ids": [a.get("anchor_id") for a in anchors],
                "feature_sources": ["symbol_detection", "text_detection", "line_tracing", "equipment_consolidation"],
                "feature_contract": "MINIMUM_TARGET_HIERARCHY_V1",
            },
        }
        profiles.append(profile)

    # Add traced connectivity at group level.
    symbol_to_group = {
        sid: p["group_id"]
        for p in profiles
        for sid in p["provenance"]["source_symbol_ids"]
        if sid
    }
    by_group = {p["group_id"]: p for p in profiles}
    for page in pages:
        for rel in page.get("terminal_tracing", {}).get("relations", []):
            ga = symbol_to_group.get(rel.get("source_symbol_id"))
            gb = symbol_to_group.get(rel.get("target_symbol_id"))
            if not ga or not gb or ga == gb:
                continue
            for src, dst in ((ga, gb), (gb, ga)):
                p = by_group[src]
                p["topology"]["trace_relation_count"] += 1
                p["topology"]["connected_candidate_ids"].append(dst)
    for p in profiles:
        p["topology"]["connected_candidate_ids"] = sorted(set(p["topology"]["connected_candidate_ids"]))

    # Morphological families: local evidence only, never an equipment label.
    fam_buckets: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for p in profiles:
        fam_buckets[_morph_signature(p)].append(p)
    ordered = sorted(fam_buckets.items(), key=lambda kv: repr(kv[0]))
    for idx, (_, members) in enumerate(ordered, start=1):
        fid = f"MF_{idx:04d}"
        page_counts = Counter((m["document"], m["page"]) for m in members)
        for m in members:
            m["repetition"]["morph_family_id"] = fid
            m["repetition"]["family_size"] = len(members)
            m["repetition"]["same_page_family_size"] = page_counts[(m["document"], m["page"])]

    return profiles
