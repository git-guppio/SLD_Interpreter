"""Resolve optional plant-layout information without contaminating SLD counts.

Dev7 keeps direct source text as the preferred evidence.  When a layout's native
text layer corrupts feeder labels, structural feeder trunks may still be
recovered from vector geometry.  Such lines receive synthetic grouping keys and
UNRESOLVED source labels; the code never claims that a synthetic key is the
actual drawing label.
"""
from __future__ import annotations

from collections import defaultdict, deque
from math import hypot
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _center(bbox) -> Tuple[float, float]:
    x0, y0, x1, y1 = [float(v) for v in bbox]
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _node_point(n: Dict[str, Any]) -> Tuple[float, float]:
    p = n.get("point")
    if isinstance(p, dict):
        return float(p.get("x", 0.0)), float(p.get("y", 0.0))
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return float(p[0]), float(p[1])
    return 0.0, 0.0


def _component_map(page: Dict[str, Any]) -> Dict[int, int]:
    graph = page.get("planar_graph", {}) or {}
    nodes = graph.get("nodes", []) or []
    edges = graph.get("edges", []) or []
    ids = [int(n.get("node_id")) for n in nodes if n.get("node_id") is not None]
    adj: Dict[int, set[int]] = {i: set() for i in ids}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s is None or t is None:
            continue
        s, t = int(s), int(t)
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)
    comp: Dict[int, int] = {}
    cid = 0
    for n in adj:
        if n in comp:
            continue
        q = deque([n])
        comp[n] = cid
        while q:
            u = q.popleft()
            for v in adj.get(u, ()):
                if v not in comp:
                    comp[v] = cid
                    q.append(v)
        cid += 1
    return comp


def _nearest_component(page: Dict[str, Any], bbox, max_fraction: float = 0.030) -> Dict[str, Any]:
    graph = page.get("planar_graph", {}) or {}
    nodes = graph.get("nodes", []) or []
    if not nodes or not bbox:
        return {"component_id": None, "node_id": None, "distance_pt": None, "status": "NO_GRAPH_OR_BBOX"}
    comp = _component_map(page)
    c = _center(bbox)
    ranked = []
    for n in nodes:
        nid = n.get("node_id")
        if nid is None:
            continue
        p = _node_point(n)
        ranked.append((hypot(c[0]-p[0], c[1]-p[1]), int(nid)))
    if not ranked:
        return {"component_id": None, "node_id": None, "distance_pt": None, "status": "NO_GRAPH_NODES"}
    ranked.sort()
    d, nid = ranked[0]
    diag = hypot(float(page.get("page_width_pt") or 1.0), float(page.get("page_height_pt") or 1.0))
    max_d = max(18.0, diag * max_fraction)
    if d > max_d:
        return {"component_id": None, "node_id": nid, "distance_pt": round(d, 3), "status": "TOO_FAR_FROM_GRAPH"}
    return {"component_id": comp.get(nid), "node_id": nid, "distance_pt": round(d, 3), "status": "BOUND_TO_GRAPH"}


def _feeder_x(row: Dict[str, Any]) -> Optional[float]:
    trunk = row.get("trunk", {}) or {}
    if trunk.get("x") is not None:
        return float(trunk["x"])
    bbox = row.get("bbox")
    return _center(bbox)[0] if bbox else None


def _structural_assignment(cu: Dict[str, Any], feeders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Assign a CU to a recovered feeder only under strong column separation."""
    if not feeders or not cu.get("bbox"):
        return None
    cx = _center(cu["bbox"])[0]
    fx = sorted((float(_feeder_x(f)), f) for f in feeders if _feeder_x(f) is not None)
    if not fx:
        return None
    spacings = [fx[i+1][0] - fx[i][0] for i in range(len(fx)-1) if fx[i+1][0] > fx[i][0]]
    spacing = median(spacings) if spacings else None
    ranked = sorted((abs(cx-x), x, f) for x, f in fx)
    d1, x1, f1 = ranked[0]
    d2 = ranked[1][0] if len(ranked) > 1 else None
    if spacing is not None:
        if d1 > max(30.0, 0.38 * spacing):
            return None
        if d2 is not None and (d2 - d1) < max(12.0, 0.15 * spacing):
            return None
    return {
        "feeder": f1,
        "distance_x_pt": round(d1, 3),
        "median_feeder_spacing_pt": round(float(spacing), 3) if spacing is not None else None,
    }



def _select_operator_line_mapping(
    operator_feedback: Iterable[Dict[str, Any]] | None,
    learned_patterns: Iterable[Dict[str, Any]] | None,
    *,
    plant_id: Optional[str],
) -> Tuple[Dict[str, str], Optional[str], Optional[str]]:
    """Return synthetic-feeder -> operator label mapping.

    Current-run operator feedback has precedence.  Learned mappings are reused
    only for the exact plant that taught them; dev8 intentionally does not
    generalize left-to-right line numbering across plants.
    """
    for fb in operator_feedback or []:
        if fb.get("status") != "OPERATOR_PROVIDED" or fb.get("target") != "MV_LINE_LABEL_MAPPING":
            continue
        fb_plant = fb.get("plant_id") or (fb.get("context", {}) or {}).get("plant_id")
        if plant_id and fb_plant and str(fb_plant) != str(plant_id):
            continue
        value = fb.get("value")
        if isinstance(value, dict) and value:
            return ({str(k): str(v) for k, v in value.items()}, "OPERATOR_PROVIDED", fb.get("request_id"))

    for pat in learned_patterns or []:
        if not pat.get("enabled", True) or pat.get("pattern_type") != "MV_LINE_LABEL_MAPPING":
            continue
        if str(pat.get("scope", "")).upper() not in {"PLANT", "DOCUMENT"}:
            continue
        if plant_id and str(pat.get("origin_plant_id")) != str(plant_id):
            continue
        value = pat.get("mapping")
        if isinstance(value, dict) and value:
            return ({str(k): str(v) for k, v in value.items()}, "LEARNED_OPERATOR_PATTERN", pat.get("pattern_id"))
    return {}, None, None


def build_layout_resolution_requests(
    layout_resolution: Dict[str, Any],
    *,
    plant_id: Optional[str] = None,
    operator_feedback: Iterable[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Create one grouped operator request for unresolved MV feeder labels."""
    unresolved = list((layout_resolution or {}).get("unresolved_line_labels", []) or [])
    if not unresolved:
        return []
    request_id = f"{plant_id or 'PLANT'}::REQ::MV_LINE_LABEL_MAPPING"
    answered = {
        fb.get("request_id") for fb in (operator_feedback or [])
        if fb.get("request_id") and fb.get("status") == "OPERATOR_PROVIDED"
    }
    if request_id in answered:
        return []
    ordered = sorted(unresolved, key=lambda r: str(r.get("synthetic_line_key") or ""))
    return [{
        "request_id": request_id,
        "target": "MV_LINE_LABEL_MAPPING",
        "reason": "STRUCTURAL_MV_FEEDERS_RESOLVED_BUT_NATIVE_LINE_LABELS_UNREADABLE",
        "doc": (layout_resolution.get("conversion_unit_representations") or [{}])[0].get("doc"),
        "page": ordered[0].get("page") if len({r.get("page") for r in ordered}) == 1 else None,
        "group_ids": [str(r.get("synthetic_line_key")) for r in ordered],
        "candidate_values": [],
        "interaction_mode": "PROVIDE_VALUE",
        "required_for": "PLANT_MV_TOPOLOGY_LABELING",
        "status": "OPEN",
        "context": {
            "plant_id": plant_id,
            "mapping_keys": [str(r.get("synthetic_line_key")) for r in ordered],
            "feeders": ordered,
            "operator_options": ["PROVIDE_VALUE", "UNABLE_TO_IDENTIFY"],
            "note": "Provide the actual source label for each synthetic feeder key. The order is evidence only; no left-to-right numbering is assumed automatically.",
        },
    }]


def resolve_layout(
    layout_pages: List[Dict[str, Any]],
    *,
    operator_feedback: Iterable[Dict[str, Any]] | None = None,
    learned_patterns: Iterable[Dict[str, Any]] | None = None,
    plant_id: Optional[str] = None,
    supplemental_cu_representations: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    if not layout_pages:
        return {
            "present": False,
            "mv_lines": [],
            "conversion_unit_representations": [],
            "cu_mv_membership": [],
            "unresolved_membership": [],
            "unresolved_line_labels": [],
            "operator_feedback_diagnostics": [],
            "policy": "OPTIONAL_LAYOUT_SOURCE_ABSENT",
        }

    cu_reps: List[Dict[str, Any]] = []
    line_reps: List[Dict[str, Any]] = []
    feeder_reps: List[Dict[str, Any]] = []
    supplemental_cu_representations = list(supplemental_cu_representations or [])

    page_index = {p.get("page"): p for p in layout_pages}

    for page in layout_pages:
        cu_anchors = [
            a for a in page.get("text_equipment_anchors", []) or []
            if a.get("equipment_type") == "CONVERSION_UNIT"
            and a.get("anchor_role") in {"INSTANCE", "TAG"}
            and (a.get("attributes", {}) or {}).get("instance_hint") is not None
        ]
        for a in cu_anchors:
            bind = _nearest_component(page, a.get("bbox"))
            cu_reps.append({
                "cu_instance_key": str((a.get("attributes", {}) or {}).get("instance_hint")),
                "page": page.get("page"),
                "doc": page.get("doc"),
                "anchor_id": a.get("anchor_id"),
                "text": a.get("text"),
                "bbox": a.get("bbox"),
                "graph_binding": bind,
                "source_status": "DETECTED",
            })

        for a in page.get("layout_mv_line_anchors", []) or []:
            if a.get("anchor_role") != "INSTANCE" or a.get("line_instance_hint") is None:
                continue
            bind = _nearest_component(page, a.get("bbox"))
            line_reps.append({
                "line_instance_key": str(a.get("line_instance_hint")),
                "page": page.get("page"),
                "doc": page.get("doc"),
                "anchor_id": a.get("anchor_id"),
                "text": a.get("text"),
                "bbox": a.get("bbox"),
                "graph_binding": bind,
                "source_status": "DETECTED",
                "label_status": "RESOLVED",
            })

        for f in page.get("layout_feeder_candidates", []) or []:
            row = dict(f)
            row["page"] = page.get("page")
            row["doc"] = page.get("doc")
            feeder_reps.append(row)

    # Document-local cross-source resolution may establish that a representation
    # such as XFR_27 denotes the same Power Block/CU instance in this plant.
    # This mapping is supplied explicitly and is never assumed globally.
    existing_rep_keys = {(r.get("page"), str(r.get("cu_instance_key")), r.get("anchor_id")) for r in cu_reps}
    for r0 in supplemental_cu_representations:
        r = dict(r0)
        key = (r.get("page"), str(r.get("cu_instance_key")), r.get("anchor_id"))
        if key in existing_rep_keys:
            continue
        page = page_index.get(r.get("page"))
        if page and r.get("bbox") and not (r.get("graph_binding") or {}).get("status"):
            r["graph_binding"] = _nearest_component(page, r.get("bbox"))
        cu_reps.append(r)
        existing_rep_keys.add(key)

    # Direct, readable source labels always win.
    lines_by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in line_reps:
        lines_by_key[r["line_instance_key"]].append(r)
    mv_lines: List[Dict[str, Any]] = [{
        "line_id": f"MV_LINE::{k}",
        "instance_key": k,
        "synthetic_line_key": None,
        "label_status": "RESOLVED",
        "source_status": "DETECTED",
        "representations": reps,
    } for k, reps in sorted(lines_by_key.items())]

    # If source labels are unreadable but high-coherence structural feeder trunks
    # exist, preserve the topology under synthetic keys.  This is not source-label
    # recognition; label_status remains UNRESOLVED.
    if not mv_lines and feeder_reps:
        for f in sorted(feeder_reps, key=lambda r: (r.get("page") or 0, _feeder_x(r) or 0.0)):
            sk = str(f.get("synthetic_line_key"))
            mv_lines.append({
                "line_id": f"MV_LINE::{sk}",
                "instance_key": None,
                "synthetic_line_key": sk,
                "label_status": "UNRESOLVED",
                "source_status": "INFERRED",
                "representations": [f],
            })

    line_label_map, line_label_map_source, line_label_map_ref = _select_operator_line_mapping(
        operator_feedback, learned_patterns, plant_id=plant_id
    )
    operator_feedback_diagnostics: List[Dict[str, Any]] = []
    known_synthetic = {str(l.get("synthetic_line_key")) for l in mv_lines if l.get("synthetic_line_key")}
    if line_label_map:
        unknown_keys = sorted(set(line_label_map) - known_synthetic)
        if unknown_keys:
            operator_feedback_diagnostics.append({
                "status": "PARTIAL_MAPPING_WITH_UNKNOWN_FEEDER_KEYS",
                "unknown_keys": unknown_keys,
                "source_status": line_label_map_source,
                "mapping_ref": line_label_map_ref,
            })
        for line in mv_lines:
            sk = line.get("synthetic_line_key")
            if sk and str(sk) in line_label_map:
                label = str(line_label_map[str(sk)]).strip()
                line["instance_key"] = label
                line["resolved_label"] = label
                line["label_status"] = "RESOLVED"
                line["label_source_status"] = line_label_map_source
                line["operator_mapping_ref"] = line_label_map_ref
        operator_feedback_diagnostics.append({
            "status": "MV_LINE_LABEL_MAPPING_APPLIED",
            "mapped_count": sum(1 for l in mv_lines if l.get("label_status") == "RESOLVED" and l.get("synthetic_line_key")),
            "source_status": line_label_map_source,
            "mapping_ref": line_label_map_ref,
        })

    resolved_label_by_synthetic = {
        str(l.get("synthetic_line_key")): str(l.get("instance_key"))
        for l in mv_lines
        if l.get("synthetic_line_key") and l.get("label_status") == "RESOLVED" and l.get("instance_key") is not None
    }

    # Explicit graph-based relation remains the strongest automatic membership.
    line_by_pc: Dict[Tuple[Any, Any], set[str]] = defaultdict(set)
    for r in line_reps:
        b = r.get("graph_binding", {}) or {}
        if b.get("status") == "BOUND_TO_GRAPH" and b.get("component_id") is not None:
            line_by_pc[(r.get("page"), b.get("component_id"))].add(r["line_instance_key"])

    membership: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    assigned_cu = set()

    for cu in cu_reps:
        b = cu.get("graph_binding", {}) or {}
        line_keys = []
        if b.get("status") == "BOUND_TO_GRAPH" and b.get("component_id") is not None:
            line_keys = sorted(line_by_pc.get((cu.get("page"), b.get("component_id")), set()))
        if len(line_keys) == 1:
            membership.append({
                "cu_instance_key": cu["cu_instance_key"],
                "mv_line_instance_key": line_keys[0],
                "source_status": "INFERRED",
                "basis": "EXPLICIT_LINE_ID_PLUS_SHARED_GRAPH_COMPONENT",
                "page": cu.get("page"),
                "graph_component_id": b.get("component_id"),
                "cu_anchor_id": cu.get("anchor_id"),
                "line_label_status": "RESOLVED",
            })
            assigned_cu.add((cu.get("page"), cu["cu_instance_key"], cu.get("anchor_id")))

    # Structural fallback: use only feeder trunks recovered as top-level repeated
    # conductors.  CU-to-feeder alignment must be unambiguous relative to the
    # median feeder spacing.  This is stronger than generic proximity alone.
    feeders_by_page: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for f in feeder_reps:
        feeders_by_page[f.get("page")].append(f)

    for cu in cu_reps:
        ckey = (cu.get("page"), cu["cu_instance_key"], cu.get("anchor_id"))
        if ckey in assigned_cu:
            continue
        feeders = feeders_by_page.get(cu.get("page"), [])
        a = _structural_assignment(cu, feeders)
        if a:
            f = a["feeder"]
            sk = str(f.get("synthetic_line_key"))
            mapped_label = resolved_label_by_synthetic.get(sk)
            membership.append({
                "cu_instance_key": cu["cu_instance_key"],
                "mv_line_instance_key": mapped_label or sk,
                "synthetic_line_key": sk,
                "source_status": "INFERRED",
                "basis": "STRUCTURAL_FEEDER_TRUNK_PLUS_UNAMBIGUOUS_COLUMN_ALIGNMENT",
                "page": cu.get("page"),
                "cu_anchor_id": cu.get("anchor_id"),
                "feeder_candidate_id": f.get("candidate_id"),
                "line_label_status": "RESOLVED" if mapped_label else "UNRESOLVED",
                "line_label_source_status": line_label_map_source if mapped_label else None,
                "alignment": {
                    "distance_x_pt": a["distance_x_pt"],
                    "median_feeder_spacing_pt": a["median_feeder_spacing_pt"],
                },
            })
            assigned_cu.add(ckey)
            continue

        reason = "NO_EXPLICIT_MV_LINE_ID_OR_UNAMBIGUOUS_STRUCTURAL_FEEDER"
        if b.get("status") != "BOUND_TO_GRAPH":
            reason = "CU_LAYOUT_LABEL_NOT_BOUND_TO_ELECTRICAL_GRAPH_AND_NO_STRUCTURAL_FEEDER_MATCH"
        unresolved.append({
            "cu_instance_key": cu["cu_instance_key"],
            "page": cu.get("page"),
            "reason": reason,
            "graph_component_id": b.get("component_id"),
            "anchor_id": cu.get("anchor_id"),
        })

    # Canonicalize representation-level membership to CU-level membership.
    # A CU may appear on multiple layout pages.  Repeated representations of the
    # same relation are one plant-level relation; contradictory line assignments
    # remain unresolved rather than being arbitrarily selected.
    mem_by_cu: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in membership:
        mem_by_cu[str(m.get("cu_instance_key"))].append(m)
    canonical_membership: List[Dict[str, Any]] = []
    membership_conflicts: List[Dict[str, Any]] = []
    for cu_key, rows in mem_by_cu.items():
        line_keys = sorted({str(r.get("mv_line_instance_key")) for r in rows if r.get("mv_line_instance_key") is not None})
        if len(line_keys) == 1:
            row = dict(rows[0])
            row["representation_evidence_count"] = len(rows)
            canonical_membership.append(row)
        elif len(line_keys) > 1:
            membership_conflicts.append({
                "cu_instance_key": cu_key,
                "reason": "CONFLICTING_LAYOUT_MV_LINE_ASSIGNMENTS",
                "candidate_mv_line_instance_keys": line_keys,
                "representation_evidence_count": len(rows),
            })

    resolved_cu_keys = {str(m.get("cu_instance_key")) for m in canonical_membership}
    unresolved_by_cu: Dict[str, Dict[str, Any]] = {}
    for u in unresolved:
        key = str(u.get("cu_instance_key"))
        if key in resolved_cu_keys:
            continue
        row = unresolved_by_cu.setdefault(key, dict(u))
        row["representation_evidence_count"] = row.get("representation_evidence_count", 0) + 1
    for c in membership_conflicts:
        unresolved_by_cu[str(c.get("cu_instance_key"))] = c
    membership = sorted(canonical_membership, key=lambda r: (not str(r.get("cu_instance_key")).isdigit(), int(r.get("cu_instance_key")) if str(r.get("cu_instance_key")).isdigit() else str(r.get("cu_instance_key"))))
    unresolved = sorted(unresolved_by_cu.values(), key=lambda r: (not str(r.get("cu_instance_key")).isdigit(), int(r.get("cu_instance_key")) if str(r.get("cu_instance_key")).isdigit() else str(r.get("cu_instance_key"))))

    unresolved_line_labels = [
        {
            "synthetic_line_key": l.get("synthetic_line_key"),
            "line_id": l.get("line_id"),
            "page": (l.get("representations") or [{}])[0].get("page"),
            "bbox": (l.get("representations") or [{}])[0].get("bbox"),
            "raw_header_text": (l.get("representations") or [{}])[0].get("raw_header_text"),
            "reason": "NATIVE_TEXT_LABEL_UNREADABLE",
        }
        for l in mv_lines if l.get("label_status") == "UNRESOLVED"
    ]

    return {
        "present": True,
        "mv_lines": mv_lines,
        "conversion_unit_representations": cu_reps,
        "cu_mv_membership": membership,
        "unresolved_membership": unresolved,
        "unresolved_line_labels": unresolved_line_labels,
        "operator_feedback_diagnostics": operator_feedback_diagnostics,
        "summary": {
            "layout_cu_representation_count": len(cu_reps),
            "mv_line_count": len(mv_lines),
            "resolved_cu_mv_membership_count": len(membership),
            "unresolved_cu_mv_membership_count": len(unresolved),
            "unresolved_mv_line_label_count": len(unresolved_line_labels),
            "resolved_mv_line_label_count": sum(1 for l in mv_lines if l.get("label_status") == "RESOLVED"),
            "operator_or_learned_mv_line_label_count": sum(1 for l in mv_lines if l.get("label_source_status") in {"OPERATOR_PROVIDED", "LEARNED_OPERATOR_PATTERN"}),
            "structural_feeder_candidate_count": len(feeder_reps),
        },
        "policy": (
            "LAYOUT_IS_AUXILIARY;_DIRECT_LINE_TEXT_IS_PREFERRED;_WHEN_LABEL_TEXT_IS_UNREADABLE_"
            "STRUCTURAL_FEEDER_TRUNKS_MAY_GROUP_CUS_WITH_SYNTHETIC_KEYS;_OPERATOR_OR_PLANT_SCOPED_LEARNED_MAPPING_MAY_RESOLVE_LABELS_WITH_EXPLICIT_PROVENANCE"
        ),
    }
