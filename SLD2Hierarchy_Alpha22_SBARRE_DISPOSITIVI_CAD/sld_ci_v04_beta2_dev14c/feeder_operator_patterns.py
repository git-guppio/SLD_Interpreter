"""Operator-assisted graph calibration for feeder tracing (dev11).

The operator does not enter CU membership.  They may instead teach two narrow,
plant-scoped facts:

* where the MV electrical terminal of a repeated XFR tag is located relative to
  the tag text (XFR terminal binding pattern);
* that two visible conductor endpoints separated by an inline conductive symbol
  belong to the same electrical path (conductive gap bridge pattern).

These patterns are advisory and plant-scoped.  They are applied only to the SLD
planar graph and never create target equipment identities or CU membership.
"""
from __future__ import annotations

from collections import defaultdict, deque
from math import hypot
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _pt(v: Any) -> Tuple[float, float]:
    if isinstance(v, dict):
        return float(v.get("x", 0.0)), float(v.get("y", 0.0))
    return float(v[0]), float(v[1])


def bbox_center(bbox: Iterable[float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = [float(x) for x in bbox]
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def nearest_graph_node(page: Dict[str, Any], point: Iterable[float], max_distance_pt: float = 30.0) -> Optional[Dict[str, Any]]:
    px, py = [float(x) for x in point]
    ranked = []
    for n in (page.get("planar_graph", {}) or {}).get("nodes", []) or []:
        if n.get("node_id") is None:
            continue
        x, y = _pt(n.get("point"))
        ranked.append((hypot(px - x, py - y), int(n["node_id"]), x, y, n.get("node_type")))
    if not ranked:
        return None
    ranked.sort()
    d, nid, x, y, ntype = ranked[0]
    if d > float(max_distance_pt):
        return None
    return {"node_id": nid, "point": [x, y], "distance_pt": round(d, 3), "node_type": ntype}


def _plant_matches(pattern: Dict[str, Any], plant_id: Optional[str]) -> bool:
    p = pattern.get("origin_plant_id") or pattern.get("plant_id") or (pattern.get("context", {}) or {}).get("plant_id")
    if p is None:
        return False
    return str(p) == str(plant_id)


def collect_operator_graph_patterns(
    operator_feedback: Iterable[Dict[str, Any]] = (),
    learned_patterns: Iterable[Dict[str, Any]] = (),
    *,
    plant_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    xfr: List[Dict[str, Any]] = []
    roots: List[Dict[str, Any]] = []
    bridges: List[Dict[str, Any]] = []
    instance_bridges: List[Dict[str, Any]] = []
    breakpoint_reviews: List[Dict[str, Any]] = []

    for fb in operator_feedback or []:
        if fb.get("status") != "OPERATOR_PROVIDED" or fb.get("target") != "FEEDER_ELECTRICAL_PATH_VERIFICATION":
            continue
        if plant_id is not None and not _plant_matches(fb, plant_id):
            continue
        value = fb.get("value") or {}
        if not isinstance(value, dict):
            continue
        action = value.get("action")
        row = dict(value)
        row["origin"] = "OPERATOR_PROVIDED"
        row["pattern_id"] = fb.get("request_id")
        if action == "BIND_XFR_MV_TERMINAL_PATTERN":
            xfr.append(row)
        elif action == "BIND_FEEDER_ROOT_PATTERN":
            roots.append(row)
        elif action == "ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN":
            bridges.append(row)
        elif action == "ADD_FEEDER_GRAPH_BRIDGE_INSTANCE":
            instance_bridges.append(row)
        elif action == "CLASSIFY_FEEDER_BREAKPOINT":
            breakpoint_reviews.append(row)

    for pat in learned_patterns or []:
        if not pat.get("enabled", True) or not _plant_matches(pat, plant_id):
            continue
        ptype = pat.get("pattern_type")
        row = dict(pat)
        row["origin"] = "LEARNED_FROM_OPERATOR"
        if ptype == "XFR_MV_TERMINAL_BINDING_PATTERN":
            xfr.append(row)
        elif ptype == "FEEDER_ROOT_BINDING_PATTERN":
            roots.append(row)
        elif ptype == "CONDUCTIVE_GAP_BRIDGE_PATTERN":
            bridges.append(row)

    def _dedupe(rows: List[Dict[str, Any]], fields: Tuple[str, ...]) -> List[Dict[str, Any]]:
        out_rows = []
        seen = set()
        for row in rows:
            key = tuple(str(row.get(f)) for f in fields)
            if key in seen:
                continue
            seen.add(key)
            out_rows.append(row)
        return out_rows

    # A feedback item may be present both in the current run and in the
    # plant-scoped knowledge store derived from a previous run.  Apply it once.
    xfr = _dedupe(xfr, ("offset_from_tag_center_pt", "max_snap_distance_pt"))
    roots = _dedupe(roots, ("offset_from_line_anchor_center_pt", "anchor_style", "max_snap_distance_pt"))
    bridges = _dedupe(bridges, ("orientation", "gap_length_pt", "context_class"))
    instance_bridges = _dedupe(instance_bridges, ("page", "point_a", "point_b", "feeder_id"))
    breakpoint_reviews = _dedupe(breakpoint_reviews, ("page", "source_node_id", "target_node_id", "feeder_id"))

    return {"xfr_terminal_patterns": xfr, "feeder_root_patterns": roots, "conductive_gap_bridge_patterns": bridges, "instance_bridges": instance_bridges, "breakpoint_reviews": breakpoint_reviews}


def bind_xfr_terminals(
    sld_pages: Iterable[Dict[str, Any]],
    patterns: Iterable[Dict[str, Any]],
    *,
    default_snap_distance_pt: float = 32.0,
) -> Dict[str, List[Dict[str, Any]]]:
    """Apply one or more operator-taught tag->MV-terminal offsets.

    Multiple examples are allowed because one document may use more than one
    repeated XFR drawing family. For each XFR occurrence, the closest valid
    predicted graph-node binding wins.
    """
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    pats = []
    for pat in patterns or []:
        offset = pat.get("offset_from_tag_center_pt")
        if isinstance(offset, (list, tuple)) and len(offset) == 2:
            pats.append(pat)
    if not pats:
        return out

    for page in sld_pages or []:
        for a in page.get("text_equipment_anchors", []) or []:
            attrs = a.get("attributes", {}) or {}
            key = attrs.get("xfr_instance_hint")
            if a.get("evidence_kind") != "XFR_TAG" or key is None or not a.get("bbox"):
                continue
            cx, cy = bbox_center(a["bbox"])
            ranked = []
            for pat in pats:
                dx, dy = [float(x) for x in pat["offset_from_tag_center_pt"]]
                predicted = [cx + dx, cy + dy]
                snap = float(pat.get("max_snap_distance_pt") or default_snap_distance_pt)
                bound = nearest_graph_node(page, predicted, max_distance_pt=snap)
                if bound is None:
                    continue
                ranked.append((float(bound["distance_pt"]), pat, predicted, bound))
            if not ranked:
                continue
            ranked.sort(key=lambda x: x[0])
            _, pat, predicted, bound = ranked[0]
            out[str(key)].append({
                "xfr_instance_key": str(key),
                "page": page.get("page"),
                "doc": page.get("doc"),
                "tag_bbox": a.get("bbox"),
                "predicted_terminal_point": [round(predicted[0], 3), round(predicted[1], 3)],
                "graph_node_id": bound["node_id"],
                "graph_node_point": bound["point"],
                "snap_distance_pt": bound["distance_pt"],
                "status": "OPERATOR_PATTERN_BOUND",
                "provenance": pat.get("origin", "OPERATOR_PROVIDED"),
                "pattern_id": pat.get("pattern_id"),
            })
    return out

def line_anchor_style(text: Any) -> str:
    raw = str(text or "").strip().upper()
    if "_" in raw or "-" in raw:
        return "DELIMITED"
    return "COMPACT"


def bind_feeder_roots(
    sld_pages: Iterable[Dict[str, Any]],
    patterns: Iterable[Dict[str, Any]],
    *,
    default_snap_distance_pt: float = 36.0,
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    pats = [p for p in (patterns or []) if isinstance(p.get("offset_from_line_anchor_center_pt"), (list, tuple))]
    if not pats:
        return out
    for page in sld_pages or []:
        for a in page.get("layout_mv_line_anchors", []) or []:
            line = a.get("line_instance_hint")
            if a.get("anchor_role") != "INSTANCE" or not line or not a.get("bbox"):
                continue
            style = line_anchor_style(a.get("text"))
            cx, cy = bbox_center(a["bbox"])
            ranked = []
            for pat in pats:
                if pat.get("anchor_style") and str(pat.get("anchor_style")) != style:
                    continue
                dx, dy = [float(x) for x in pat["offset_from_line_anchor_center_pt"]]
                predicted = [cx + dx, cy + dy]
                bound = nearest_graph_node(page, predicted, max_distance_pt=float(pat.get("max_snap_distance_pt") or default_snap_distance_pt))
                if bound is not None:
                    ranked.append((float(bound["distance_pt"]), pat, predicted, bound))
            if not ranked:
                continue
            ranked.sort(key=lambda x:x[0]); _, pat, predicted, bound = ranked[0]
            out[str(line)].append({
                "feeder_id": str(line), "page": page.get("page"), "anchor_text": a.get("text"),
                "anchor_bbox": a.get("bbox"), "predicted_root_point": [round(predicted[0],3),round(predicted[1],3)],
                "graph_node_id": bound["node_id"], "graph_node_point": bound["point"], "snap_distance_pt": bound["distance_pt"],
                "status": "OPERATOR_PATTERN_BOUND", "provenance": pat.get("origin","OPERATOR_PROVIDED"), "pattern_id": pat.get("pattern_id"),
            })
    return out


def _graph_edges(page: Dict[str, Any]) -> Tuple[Dict[int, set[int]], Dict[int, Tuple[float, float]], Dict[int, str]]:
    adj: Dict[int, set[int]] = defaultdict(set)
    pos: Dict[int, Tuple[float, float]] = {}
    ntype: Dict[int, str] = {}
    for n in (page.get("planar_graph", {}) or {}).get("nodes", []) or []:
        if n.get("node_id") is None:
            continue
        nid = int(n["node_id"])
        pos[nid] = _pt(n.get("point"))
        ntype[nid] = str(n.get("node_type") or "")
        adj.setdefault(nid, set())
    for e in (page.get("planar_graph", {}) or {}).get("edges", []) or []:
        if e.get("source") is None or e.get("target") is None:
            continue
        s, t = int(e["source"]), int(e["target"])
        adj[s].add(t); adj[t].add(s)
    return adj, pos, ntype


def _endpoint_nodes(adj: Dict[int, set[int]]) -> List[int]:
    return [n for n, nb in adj.items() if len(nb) <= 1]


def apply_instance_bridges(page: Dict[str, Any], records: Iterable[Dict[str, Any]], *, base_adjacency: Optional[Dict[int, set[int]]] = None) -> Dict[str, Any]:
    adj, pos, _ = _graph_edges(page)
    if base_adjacency is not None:
        adj = defaultdict(set, {int(k): set(v) for k, v in base_adjacency.items()})
    added = []
    pno = int(page.get("page") or 0)
    for rec in records or []:
        if rec.get("page") is not None and int(rec.get("page")) != pno:
            continue
        a = nearest_graph_node(page, rec.get("point_a") or [], max_distance_pt=float(rec.get("max_snap_distance_pt") or 24.0))
        b = nearest_graph_node(page, rec.get("point_b") or [], max_distance_pt=float(rec.get("max_snap_distance_pt") or 24.0))
        if not a or not b or a["node_id"] == b["node_id"]:
            continue
        u, v = int(a["node_id"]), int(b["node_id"])
        if v not in adj[u]:
            adj[u].add(v); adj[v].add(u)
            added.append({
                "source": u, "target": v, "p1": a["point"], "p2": b["point"],
                "status": "OPERATOR_INSTANCE_BRIDGE", "provenance": rec.get("origin","OPERATOR_PROVIDED"),
                "feeder_id": rec.get("feeder_id"), "page": pno,
            })
    return {"adjacency": adj, "positions": pos, "added_bridges": added}


def apply_conductive_gap_patterns(
    page: Dict[str, Any],
    patterns: Iterable[Dict[str, Any]],
    *,
    focus_points: Optional[Iterable[Iterable[float]]] = None,
) -> Dict[str, Any]:
    """Return an augmented adjacency with conservative repeated gap bridges.

    A learned bridge is characterized by orientation and gap length. Candidate
    bridges are only made between graph endpoints, are near-collinear, are not
    already adjacent, and must closely match the operator-selected gap length.
    This is intentionally plant-scoped and page-role restricted upstream.
    """
    adj, pos, ntype = _graph_edges(page)
    added: List[Dict[str, Any]] = []
    endpoints = _endpoint_nodes(adj)
    focus = [tuple(float(x) for x in p) for p in (focus_points or [])]

    for pat in patterns or []:
        orient = str(pat.get("orientation") or "").upper()
        gap = float(pat.get("gap_length_pt") or 0.0)
        if orient not in {"H", "V"} or gap <= 0:
            continue
        axis_tol = float(pat.get("axis_tolerance_pt") or max(2.5, gap * 0.18))
        gap_tol = float(pat.get("gap_tolerance_pt") or max(2.5, gap * 0.22))
        max_gap = gap + gap_tol
        min_gap = max(0.5, gap - gap_tol)

        for i, a in enumerate(endpoints):
            if a not in pos:
                continue
            ax, ay = pos[a]
            for b in endpoints[i + 1:]:
                if b not in pos or b in adj[a]:
                    continue
                bx, by = pos[b]
                # Learned repeated gap patterns are intentionally local to
                # operator-calibrated XFR MV terminal neighborhoods. This avoids
                # a short geometric gap elsewhere (including a transformer
                # winding symbol) being bridged merely because its dimensions
                # happen to match.
                context_class = str(pat.get("context_class") or "XFR_MV_TERMINAL_NEIGHBORHOOD")
                if context_class == "XFR_MV_TERMINAL_NEIGHBORHOOD":
                    if not focus:
                        continue
                    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                    radius = float(pat.get("focus_radius_pt") or 48.0)
                    if min(hypot(mx-fx, my-fy) for fx, fy in focus) > radius:
                        continue
                dx, dy = abs(bx - ax), abs(by - ay)
                if orient == "V":
                    if dx > axis_tol or not (min_gap <= dy <= max_gap):
                        continue
                    measured = dy
                else:
                    if dy > axis_tol or not (min_gap <= dx <= max_gap):
                        continue
                    measured = dx
                # Do not add an edge if the nodes are already connected by any
                # short existing path. The bridge must repair a genuine gap.
                if _reachable(adj, a, b, max_nodes=80):
                    continue
                adj[a].add(b); adj[b].add(a)
                added.append({
                    "source": a,
                    "target": b,
                    "p1": [ax, ay],
                    "p2": [bx, by],
                    "orientation": orient,
                    "gap_length_pt": round(measured, 3),
                    "status": "OPERATOR_PATTERN_BRIDGE",
                    "provenance": pat.get("origin", "OPERATOR_PROVIDED"),
                    "pattern_id": pat.get("pattern_id"),
                })
    return {"adjacency": adj, "positions": pos, "added_bridges": added}


def _reachable(adj: Dict[int, set[int]], start: int, target: int, max_nodes: Optional[int] = None) -> bool:
    if start == target:
        return True
    q = deque([start]); seen = {start}
    while q:
        u = q.popleft()
        for v in adj.get(u, ()):
            if v == target:
                return True
            if v not in seen:
                seen.add(v); q.append(v)
                if max_nodes is not None and len(seen) > max_nodes:
                    return False
    return False


def reachable_nodes(adj: Dict[int, set[int]], starts: Iterable[int]) -> set[int]:
    q = deque(int(s) for s in starts if s is not None)
    seen = set(q)
    while q:
        u = q.popleft()
        for v in adj.get(u, ()):
            if v not in seen:
                seen.add(v); q.append(v)
    return seen


def derive_xfr_binding_value(xfr_bbox: Iterable[float], terminal_point: Iterable[float], *, feeder_id: Optional[str] = None, xfr_instance_key: Optional[str] = None, page: Optional[int] = None) -> Dict[str, Any]:
    cx, cy = bbox_center(xfr_bbox)
    tx, ty = [float(x) for x in terminal_point]
    return {
        "action": "BIND_XFR_MV_TERMINAL_PATTERN",
        "feeder_id": feeder_id,
        "xfr_instance_key": str(xfr_instance_key) if xfr_instance_key is not None else None,
        "page": page,
        "xfr_bbox": [float(x) for x in xfr_bbox],
        "terminal_point": [tx, ty],
        "offset_from_tag_center_pt": [round(tx - cx, 3), round(ty - cy, 3)],
        "max_snap_distance_pt": 32.0,
        "learning_scope": "PLANT",
    }


def derive_feeder_root_value(line_anchor_bbox: Iterable[float], root_point: Iterable[float], *, feeder_id: Optional[str] = None, anchor_text: Optional[str] = None, page: Optional[int] = None) -> Dict[str, Any]:
    cx, cy = bbox_center(line_anchor_bbox); rx, ry = [float(x) for x in root_point]
    return {
        "action": "BIND_FEEDER_ROOT_PATTERN", "feeder_id": feeder_id, "page": page,
        "line_anchor_bbox": [float(x) for x in line_anchor_bbox], "anchor_text": anchor_text,
        "anchor_style": line_anchor_style(anchor_text), "root_point": [rx,ry],
        "offset_from_line_anchor_center_pt": [round(rx-cx,3),round(ry-cy,3)],
        "max_snap_distance_pt": 36.0, "learning_scope": "PLANT",
    }


def derive_instance_bridge_value(point_a: Iterable[float], point_b: Iterable[float], *, feeder_id: Optional[str] = None, page: Optional[int] = None) -> Dict[str, Any]:
    ax, ay = [float(x) for x in point_a]; bx, by = [float(x) for x in point_b]
    return {
        "action": "ADD_FEEDER_GRAPH_BRIDGE_INSTANCE", "feeder_id": feeder_id, "page": page,
        "point_a": [ax,ay], "point_b": [bx,by], "max_snap_distance_pt": 24.0,
        "learning_scope": "CURRENT_DOCUMENT_ONLY",
        "warning": "EXPLICIT_CONDUCTIVE_PATH_BRIDGE_ONLY__DO_NOT_BRIDGE_TRANSFORMER_WINDINGS",
    }


def derive_bridge_value(point_a: Iterable[float], point_b: Iterable[float], *, feeder_id: Optional[str] = None, page: Optional[int] = None, xfr_instance_key: Optional[str] = None) -> Dict[str, Any]:
    ax, ay = [float(x) for x in point_a]; bx, by = [float(x) for x in point_b]
    dx, dy = abs(bx - ax), abs(by - ay)
    orient = "V" if dy >= dx else "H"
    gap = dy if orient == "V" else dx
    return {
        "action": "ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN",
        "feeder_id": feeder_id,
        "page": page,
        "xfr_instance_key": str(xfr_instance_key) if xfr_instance_key is not None else None,
        "context_class": "XFR_MV_TERMINAL_NEIGHBORHOOD",
        "focus_radius_pt": 48.0,
        "point_a": [ax, ay],
        "point_b": [bx, by],
        "orientation": orient,
        "gap_length_pt": round(gap, 3),
        "axis_tolerance_pt": round(max(2.5, gap * 0.18), 3),
        "gap_tolerance_pt": round(max(2.5, gap * 0.22), 3),
        "learning_scope": "PLANT",
        "warning": "CONDUCTIVE_INLINE_GAP_ONLY__DO_NOT_BRIDGE_TRANSFORMER_WINDINGS",
    }

# --- dev12: operator review of suggested feeder breakpoints ---

def derive_breakpoint_review_value(
    breakpoint: Dict[str, Any],
    *,
    classification: str,
    device_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an exact, non-learned operator decision for one suggested breakpoint.

    classification:
      CONDUCTIVE_CONTINUITY  -> the two endpoints are the same conductor path;
      INTERPOSED_DEVICE      -> a real electrical device is between the endpoints;
      NON_ELECTRICAL_GRAPHIC -> the endpoints belong to a non-power graphic
                                element (boundary / area / annotation);
      UNRESOLVED             -> operator cannot decide safely.

    Device reviews never imply a closed electrical state. They are retained as
    explicit device evidence and are not converted into graph bridges.
    """
    cls = str(classification or "").upper()
    if cls not in {"CONDUCTIVE_CONTINUITY", "INTERPOSED_DEVICE", "NON_ELECTRICAL_GRAPHIC", "UNRESOLVED"}:
        raise ValueError(f"Unsupported breakpoint classification: {classification}")
    a = breakpoint.get("point_a")
    b = breakpoint.get("point_b")
    if not (isinstance(a, (list, tuple)) and len(a) == 2 and isinstance(b, (list, tuple)) and len(b) == 2):
        raise ValueError("Breakpoint review requires point_a and point_b")
    out = {
        "action": "CLASSIFY_FEEDER_BREAKPOINT",
        "classification": cls,
        "feeder_id": breakpoint.get("feeder_id"),
        "page": int(breakpoint.get("page") or 1),
        "source_node_id": breakpoint.get("source_node_id"),
        "target_node_id": breakpoint.get("target_node_id"),
        "point_a": [round(float(a[0]), 3), round(float(a[1]), 3)],
        "point_b": [round(float(b[0]), 3), round(float(b[1]), 3)],
        "alignment": breakpoint.get("alignment"),
        "distance_pt": breakpoint.get("distance_pt"),
        "learning_policy": "INSTANCE_ONLY__DO_NOT_GENERALIZE",
        "classification_schema_version": 2,
    }
    if cls == "INTERPOSED_DEVICE":
        out["device_type"] = str(device_type or "UNDETERMINED").upper()
        out["device_connectivity_state"] = "UNKNOWN"
        out["topology_policy"] = "DO_NOT_BRIDGE_DEVICE__MODEL_AS_EXPLICIT_GRAPH_ELEMENT"
    elif cls == "CONDUCTIVE_CONTINUITY":
        out["topology_policy"] = "EXACT_INSTANCE_BRIDGE_ALLOWED"
    elif cls == "NON_ELECTRICAL_GRAPHIC":
        out["graphic_role"] = "NON_POWER_GRAPHIC"
        out["topology_policy"] = "EXCLUDE_FROM_FEEDER_TRACE__DO_NOT_BRIDGE"
    else:
        out["topology_policy"] = "KEEP_UNRESOLVED__DO_NOT_BRIDGE"
    return out


def breakpoint_review_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    """Stable identity for one exact breakpoint decision."""
    return (
        str(row.get("feeder_id") or ""),
        int(row.get("page") or 0),
        int(row.get("source_node_id")) if row.get("source_node_id") is not None else None,
        int(row.get("target_node_id")) if row.get("target_node_id") is not None else None,
    )
