"""Feeder membership resolution and electrical-path verification.

Dev10 separates two questions that were previously easy to conflate:

1. *Which CU belongs to which MV feeder?*  An explicit source schedule can answer
   this directly.
2. *Can that assignment be electrically traversed/verified?*  This requires graph
   evidence from the SLD, starting from the HV/MV secondary or MV bus/breaker when
   represented, and continuing downstream through the CU hierarchy.

Explicit schedules may resolve membership, but they never masquerade as a graph
trace.  The two provenance channels are preserved separately.
"""
from __future__ import annotations

from collections import defaultdict, deque
from math import hypot
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .feeder_operator_patterns import collect_operator_graph_patterns, bind_xfr_terminals, bind_feeder_roots, apply_instance_bridges, apply_conductive_gap_patterns, reachable_nodes, breakpoint_review_key


def _sort_key(v: Any):
    s = str(v)
    return (not s.isdigit(), int(s) if s.isdigit() else s)


def _center(bbox: Any) -> Tuple[float, float]:
    x0, y0, x1, y1 = [float(x) for x in bbox]
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def _node_point(node: Dict[str, Any]) -> Tuple[float, float]:
    p = node.get("point")
    if isinstance(p, dict):
        return float(p.get("x", 0.0)), float(p.get("y", 0.0))
    return float(p[0]), float(p[1])


def _component_map(page: Dict[str, Any]) -> Dict[int, int]:
    graph = page.get("planar_graph", {}) or {}
    nodes = graph.get("nodes", []) or []
    edges = graph.get("edges", []) or []
    adj: Dict[int, set[int]] = {
        int(n["node_id"]): set() for n in nodes if n.get("node_id") is not None
    }
    for e in edges:
        if e.get("source") is None or e.get("target") is None:
            continue
        s, t = int(e["source"]), int(e["target"])
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)
    comp: Dict[int, int] = {}
    cid = 0
    for nid in adj:
        if nid in comp:
            continue
        q = deque([nid])
        comp[nid] = cid
        while q:
            u = q.popleft()
            for v in adj.get(u, ()):
                if v not in comp:
                    comp[v] = cid
                    q.append(v)
        cid += 1
    return comp


def _nearest_component(page: Dict[str, Any], bbox: Any, max_fraction: float = 0.03) -> Dict[str, Any]:
    if not bbox:
        return {"status": "NO_BBOX", "component_id": None, "node_id": None}
    nodes = (page.get("planar_graph", {}) or {}).get("nodes", []) or []
    if not nodes:
        return {"status": "NO_GRAPH", "component_id": None, "node_id": None}
    comp = _component_map(page)
    cx, cy = _center(bbox)
    ranked = []
    for n in nodes:
        if n.get("node_id") is None:
            continue
        x, y = _node_point(n)
        ranked.append((hypot(cx-x, cy-y), int(n["node_id"])))
    if not ranked:
        return {"status": "NO_GRAPH", "component_id": None, "node_id": None}
    ranked.sort()
    d, nid = ranked[0]
    diag = hypot(float(page.get("page_width_pt") or 1.0), float(page.get("page_height_pt") or 1.0))
    if d > max(18.0, diag * max_fraction):
        return {"status": "TOO_FAR_FROM_GRAPH", "component_id": None, "node_id": nid, "distance_pt": round(d, 3)}
    return {
        "status": "BOUND_TO_GRAPH",
        "component_id": comp.get(nid),
        "node_id": nid,
        "distance_pt": round(d, 3),
    }


def _explicit_schedule_memberships(layout_pages: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_cu: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for page in layout_pages or []:
        for row in page.get("mv_circuit_schedule_rows", []) or []:
            cu = str(row.get("block_instance_key"))
            line = str(row.get("mv_line_instance_key"))
            if not cu or not line:
                continue
            by_cu[cu].append({
                "cu_instance_key": cu,
                "mv_line_instance_key": line,
                "source_status": "DETECTED",
                "basis": "EXPLICIT_MV_CIRCUIT_SCHEDULE",
                "page": row.get("page"),
                "doc": row.get("doc"),
                "schedule_row": row,
                "line_label_status": "RESOLVED",
            })

    resolved: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    for cu in sorted(by_cu, key=_sort_key):
        rows = by_cu[cu]
        lines = sorted({str(r["mv_line_instance_key"]) for r in rows})
        if len(lines) == 1:
            r = dict(rows[0])
            r["representation_evidence_count"] = len(rows)
            resolved.append(r)
        else:
            conflicts.append({
                "cu_instance_key": cu,
                "status": "CONFLICT",
                "reason": "CU_LISTED_IN_MULTIPLE_EXPLICIT_MV_CIRCUIT_SCHEDULES",
                "candidate_mv_line_instance_keys": lines,
                "evidence": rows,
            })
    return resolved, conflicts


def _sld_xfr_instances(sld_pages: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for page in sld_pages or []:
        for a in page.get("text_equipment_anchors", []) or []:
            attrs = a.get("attributes", {}) or {}
            key = attrs.get("xfr_instance_hint")
            if a.get("evidence_kind") != "XFR_TAG" or key is None:
                continue
            row = dict(a)
            row["page_role"] = page.get("page_role")
            row["graph_binding"] = _nearest_component(page, a.get("bbox"))
            out[str(key)].append(row)
    return out


def _usable_sld_line_anchors(sld_pages: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Retain only local line-instance tokens useful as graph roots.

    This intentionally excludes title ranges and cable-insulation text.  A bare
    MV identifier is evidence of a line root only; it is not sufficient by itself
    to establish CU membership.
    """
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    exact = re.compile(r"^MV\s*[-_]?\s*\d{1,3}$", re.I)
    for page in sld_pages or []:
        for a in page.get("layout_mv_line_anchors", []) or []:
            if a.get("anchor_role") != "INSTANCE" or not a.get("line_instance_hint"):
                continue
            raw = " ".join(str(a.get("text") or "").strip().split())
            if not exact.fullmatch(raw):
                continue
            row = dict(a)
            row["graph_binding"] = _nearest_component(page, a.get("bbox"))
            row["page_role"] = page.get("page_role")
            out[str(a["line_instance_hint"])].append(row)
    return out


def _sld_source_root_semantics(sld_pages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    hv_mv = False
    mv_bus = False
    substation_breaker = False
    project_substation = False
    pages = []
    for p in sld_pages or []:
        sem = p.get("document_semantics", {}) or {}
        if sem.get("has_hv_mv_transformer_context"):
            hv_mv = True
        if sem.get("has_mv_busbar"):
            mv_bus = True
        if sem.get("has_substation_breaker"):
            substation_breaker = True
        if sem.get("has_project_substation"):
            project_substation = True
        if any((sem.get("has_hv_mv_transformer_context"), sem.get("has_mv_busbar"), sem.get("has_substation_breaker"), sem.get("has_project_substation"))):
            pages.append(p.get("page"))
    if hv_mv:
        origin = "HV_MV_TRANSFORMER_SECONDARY"
    elif mv_bus:
        origin = "MV_BUSBAR"
    elif substation_breaker or project_substation:
        origin = "MV_SUBSTATION_BREAKER_OR_PROJECT_SUBSTATION"
    else:
        origin = "FEEDER_LABEL_ONLY"
    return {
        "origin_type": origin,
        "hv_mv_transformer_context_present": hv_mv,
        "mv_busbar_context_present": mv_bus,
        "substation_breaker_context_present": substation_breaker,
        "project_substation_context_present": project_substation,
        "evidence_pages": sorted({p for p in pages if p is not None}),
    }


def _candidate_crosses_interposed_device(candidate: Dict[str, Any], reviews: Iterable[Dict[str, Any]]) -> bool:
    """Reject gap proposals that would geometrically bypass a reviewed device.

    Once the operator has said that a real device lies between two endpoints, a
    later wider endpoint pair on the same conductor corridor must not be offered
    as a substitute bridge around that device.
    """
    a = candidate.get("point_a"); b = candidate.get("point_b")
    if not (a and b):
        return False
    ax, ay = float(a[0]), float(a[1]); bx, by = float(b[0]), float(b[1])
    vx, vy = bx-ax, by-ay
    vv = vx*vx + vy*vy
    if vv <= 1e-9:
        return False
    for r in reviews or []:
        if str(r.get("feeder_id") or "") != str(candidate.get("feeder_id") or ""):
            continue
        if int(r.get("page") or 0) != int(candidate.get("page") or 0):
            continue
        ra, rb = r.get("point_a"), r.get("point_b")
        if not (ra and rb):
            continue
        mx = (float(ra[0]) + float(rb[0])) / 2.0
        my = (float(ra[1]) + float(rb[1])) / 2.0
        t = ((mx-ax)*vx + (my-ay)*vy) / vv
        if t < -0.02 or t > 1.02:
            continue
        px, py = ax + t*vx, ay + t*vy
        dist = hypot(mx-px, my-py)
        # Allow a few PDF points of drawing tolerance; scale slightly with the
        # reviewed device gap so long symbols still protect their corridor.
        device_gap = hypot(float(ra[0])-float(rb[0]), float(ra[1])-float(rb[1]))
        tol = max(5.0, min(14.0, device_gap * 0.35))
        if dist <= tol:
            return True
    return False


def _suggest_graph_breakpoints(
    line: str,
    reachable_by_line_page: Dict[Tuple[str, int], set[int]],
    augmented_pages: Dict[int, Dict[str, Any]],
    *,
    max_distance_pt: float = 42.0,
    limit: int = 4,
    excluded_breakpoints: Optional[set[Tuple[Any, ...]]] = None,
    blocked_device_reviews: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    suggestions: List[Tuple[float, Dict[str, Any]]] = []
    for (line_id, page_no), reached in reachable_by_line_page.items():
        if str(line_id) != str(line) or not reached:
            continue
        aug = augmented_pages.get(page_no) or {}
        adj = aug.get("adjacency") or {}; pos = aug.get("positions") or {}
        inside = [n for n in reached if n in pos and len(adj.get(n, ())) <= 1]
        outside = [n for n in pos if n not in reached and len(adj.get(n, ())) <= 1]
        for a in inside:
            ax, ay = pos[a]
            for b in outside:
                bx, by = pos[b]
                d = hypot(ax-bx, ay-by)
                if d > max_distance_pt:
                    continue
                dx, dy = abs(ax-bx), abs(ay-by)
                # Favor near-collinear gaps, which are common at inline symbols.
                alignment = "V" if dx <= 4.0 else "H" if dy <= 4.0 else "DIAGONAL"
                penalty = 0.0 if alignment != "DIAGONAL" else 12.0
                row = {
                    "page": page_no, "feeder_id": str(line),
                    "source_node_id": int(a), "target_node_id": int(b),
                    "point_a": [round(ax,3),round(ay,3)], "point_b": [round(bx,3),round(by,3)],
                    "distance_pt": round(d,3), "alignment": alignment,
                    "status": "OPERATOR_CONFIRMATION_REQUIRED",
                    "reason": "NEAREST_REACHABLE_TO_UNREACHABLE_ENDPOINT_PAIR",
                }
                key = breakpoint_review_key(row)
                if excluded_breakpoints and key in excluded_breakpoints:
                    continue
                if _candidate_crosses_interposed_device(row, blocked_device_reviews or []):
                    continue
                suggestions.append((d+penalty,row))
    suggestions.sort(key=lambda x:x[0])
    out=[]; seen=set()
    for _, row in suggestions:
        key=(row["page"],row["source_node_id"],row["target_node_id"])
        if key in seen: continue
        seen.add(key); out.append(row)
        if len(out)>=limit: break
    return out


def resolve_feeder_verification(
    sld_pages: List[Dict[str, Any]],
    layout_pages: List[Dict[str, Any]],
    *,
    template_schedule_resolution: Optional[Dict[str, Any]] = None,
    legacy_layout_resolution: Optional[Dict[str, Any]] = None,
    plant_id: Optional[str] = None,
    operator_feedback: Optional[List[Dict[str, Any]]] = None,
    learned_patterns: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    schedule_membership, schedule_conflicts = _explicit_schedule_memberships(layout_pages)
    xfr = _sld_xfr_instances(sld_pages)
    line_roots = _usable_sld_line_anchors(sld_pages)
    root_semantics = _sld_source_root_semantics(sld_pages)

    # Dev11 operator-assisted graph calibration.  These patterns never establish
    # membership: they only bind repeated XFR tags to graph terminals and heal
    # operator-confirmed conductive inline gaps on the SLD graph.
    operator_patterns = collect_operator_graph_patterns(
        operator_feedback or [], learned_patterns or [], plant_id=plant_id
    )
    breakpoint_reviews = list(operator_patterns.get("breakpoint_reviews", []) or [])
    reviewed_breakpoint_keys = {breakpoint_review_key(x) for x in breakpoint_reviews}
    confirmed_continuity_reviews = [x for x in breakpoint_reviews if str(x.get("classification") or "").upper() == "CONDUCTIVE_CONTINUITY"]
    interposed_device_reviews = [x for x in breakpoint_reviews if str(x.get("classification") or "").upper() == "INTERPOSED_DEVICE"]
    non_electrical_graphic_reviews = [x for x in breakpoint_reviews if str(x.get("classification") or "").upper() == "NON_ELECTRICAL_GRAPHIC"]
    unresolved_breakpoint_reviews = [x for x in breakpoint_reviews if str(x.get("classification") or "").upper() == "UNRESOLVED"]

    # Operator-confirmed non-electrical graphics (area boundaries, dashed
    # enclosures, annotations...) must not participate in the feeder traversal.
    # The exclusion is exact and feeder/page-scoped: it does not create a global
    # rule such as "all dashed lines are non-electrical".
    blocked_graphic_nodes_by_line_page: Dict[Tuple[str, int], set[int]] = defaultdict(set)
    for review in non_electrical_graphic_reviews:
        line = str(review.get("feeder_id") or "")
        page_no = int(review.get("page") or 0)
        if not line or not page_no:
            continue
        for key in ("source_node_id", "target_node_id"):
            nid = review.get(key)
            if nid is not None:
                blocked_graphic_nodes_by_line_page[(line, page_no)].add(int(nid))

    # Only an explicit CONDUCTIVE_CONTINUITY decision becomes an exact graph
    # bridge.  INTERPOSED_DEVICE and UNRESOLVED are never bridged.
    exact_review_bridges = [
        {
            "page": x.get("page"),
            "point_a": x.get("point_a"),
            "point_b": x.get("point_b"),
            "feeder_id": x.get("feeder_id"),
            "origin": "OPERATOR_PROVIDED",
        }
        for x in confirmed_continuity_reviews
    ]
    xfr_terminal_bindings = bind_xfr_terminals(
        sld_pages, operator_patterns.get("xfr_terminal_patterns", [])
    )
    operator_root_bindings = bind_feeder_roots(
        sld_pages, operator_patterns.get("feeder_root_patterns", [])
    )
    augmented_pages: Dict[int, Dict[str, Any]] = {}
    terminal_focus_by_page: Dict[int, List[List[float]]] = defaultdict(list)
    for rows in xfr_terminal_bindings.values():
        for tb in rows or []:
            if tb.get("page") is not None and tb.get("predicted_terminal_point"):
                terminal_focus_by_page[int(tb["page"])].append(tb["predicted_terminal_point"])
    for p in sld_pages or []:
        if p.get("page") is None:
            continue
        pno = int(p["page"])
        inst = apply_instance_bridges(
            p, list(operator_patterns.get("instance_bridges", []) or []) + exact_review_bridges
        )
        patt = apply_conductive_gap_patterns(
            p, operator_patterns.get("conductive_gap_bridge_patterns", []),
            focus_points=terminal_focus_by_page.get(pno, []),
        )
        conductive = defaultdict(set)
        for src in (inst.get("adjacency", {}), patt.get("adjacency", {})):
            for nid, nbs in src.items():
                conductive[int(nid)].update(int(x) for x in nbs)

        # dev13: a reviewed INTERPOSED_DEVICE is not a conductive gap bridge.
        # It is represented as an explicit equipment edge in a *structural*
        # topology graph.  This lets feeder tracing pass through a switchgear /
        # cabinet / other device as an asset while preserving UNKNOWN operating
        # state and without pretending the two conductor endpoints are the same
        # node.  No behavior changes when no such operator review exists.
        topology = defaultdict(set)
        for nid, nbs in conductive.items():
            topology[int(nid)].update(int(x) for x in nbs)
        positions = inst.get("positions") or patt.get("positions") or {}
        modeled_devices = []
        for review in interposed_device_reviews:
            if int(review.get("page") or 0) != pno:
                continue
            a = review.get("source_node_id"); b = review.get("target_node_id")
            if a is None or b is None:
                continue
            a = int(a); b = int(b)
            if a not in positions or b not in positions:
                continue
            topology[a].add(b); topology[b].add(a)
            modeled_devices.append({
                "source_node_id": a,
                "target_node_id": b,
                "device_type": str(review.get("device_type") or "UNDETERMINED"),
                "device_connectivity_state": str(review.get("device_connectivity_state") or "UNKNOWN"),
                "edge_semantics": "INTERPOSED_DEVICE_STRUCTURAL_TOPOLOGY",
                "conductive_bridge": False,
                "origin": str(review.get("origin") or "OPERATOR_PROVIDED"),
                "review": review,
            })

        augmented_pages[pno] = {
            # Feeder membership verification follows structural electrical
            # topology.  Conductive continuity remains available separately.
            "adjacency": topology,
            "topology_adjacency": topology,
            "conductive_adjacency": conductive,
            "positions": positions,
            "added_bridges": list(inst.get("added_bridges", []) or []) + list(patt.get("added_bridges", []) or []),
            "added_instance_bridges": list(inst.get("added_bridges", []) or []),
            "added_pattern_bridges": list(patt.get("added_bridges", []) or []),
            "modeled_interposed_devices": modeled_devices,
            "added_device_topology_edges": modeled_devices,
        }

    legacy = list((legacy_layout_resolution or {}).get("cu_mv_membership", []) or [])
    legacy_by_cu = {str(x.get("cu_instance_key")): x for x in legacy}

    schedule_by_cu = {str(x["cu_instance_key"]): x for x in schedule_membership}
    graph_verified: List[Dict[str, Any]] = []
    source_crosschecked: List[Dict[str, Any]] = []
    graph_conflicts: List[Dict[str, Any]] = []

    # Conservative graph support: only accept an existing relation explicitly
    # based on a shared graph component. Structural column alignment is not graph
    # verification.  SLD XFR presence is a separate cross-source check.
    for cu, sm in schedule_by_cu.items():
        expected = str(sm["mv_line_instance_key"])
        lm = legacy_by_cu.get(cu)
        if lm and lm.get("basis") == "EXPLICIT_LINE_ID_PLUS_SHARED_GRAPH_COMPONENT":
            actual = str(lm.get("mv_line_instance_key"))
            if actual == expected:
                graph_verified.append({
                    "cu_instance_key": cu,
                    "mv_line_instance_key": expected,
                    "status": "GRAPH_VERIFIED",
                    "basis": "EXPLICIT_SCHEDULE_PLUS_SHARED_LAYOUT_GRAPH_COMPONENT",
                    "schedule_page": sm.get("page"),
                    "graph_page": lm.get("page"),
                })
            else:
                graph_conflicts.append({
                    "cu_instance_key": cu,
                    "schedule_mv_line": expected,
                    "graph_mv_line": actual,
                    "status": "CONFLICT",
                    "reason": "EXPLICIT_SCHEDULE_DISAGREES_WITH_SHARED_GRAPH_COMPONENT",
                })

        if cu in xfr:
            source_crosschecked.append({
                "cu_instance_key": cu,
                "mv_line_instance_key": expected,
                "status": "SOURCE_CROSSCHECKED_NOT_GRAPH_VERIFIED",
                "basis": "EXPLICIT_SCHEDULE_PLUS_EXPLICIT_SLD_XFR_IDENTITY",
                "xfr_occurrence_count": len(xfr[cu]),
                "xfr_pages": sorted({r.get("page") for r in xfr[cu] if r.get("page") is not None}),
            })

    # Independent SLD graph trace using operator-taught terminal/gap patterns.
    # Root labels are still source-detected; if they cannot be bound to the graph
    # no positive verification is claimed.
    operator_graph_verified: List[Dict[str, Any]] = []
    operator_graph_conflicts: List[Dict[str, Any]] = []
    reachable_by_line_page: Dict[Tuple[str, int], set[int]] = {}
    all_lines_for_roots = sorted(set(line_roots) | set(operator_root_bindings))
    for line in all_lines_for_roots:
        by_page_roots: Dict[int, List[int]] = defaultdict(list)
        # Operator-calibrated roots are higher-quality bindings than nearest-text
        # fallback, but both may coexist as evidence.
        for r in operator_root_bindings.get(line, []) or []:
            if r.get("page") is not None and r.get("graph_node_id") is not None:
                by_page_roots[int(r["page"])].append(int(r["graph_node_id"]))
        for r in line_roots.get(line, []) or []:
            page_no = r.get("page")
            gb = r.get("graph_binding") or {}
            if page_no is None or gb.get("status") != "BOUND_TO_GRAPH" or gb.get("node_id") is None:
                continue
            by_page_roots[int(page_no)].append(int(gb["node_id"]))
        for page_no, starts in by_page_roots.items():
            aug = augmented_pages.get(page_no) or {}
            adj = aug.get("adjacency") or {}
            if adj:
                blocked = blocked_graphic_nodes_by_line_page.get((str(line), page_no), set())
                if blocked:
                    trace_adj = {
                        int(n): {int(v) for v in nbs if int(v) not in blocked}
                        for n, nbs in adj.items() if int(n) not in blocked
                    }
                    trace_starts = [int(x) for x in starts if int(x) not in blocked]
                else:
                    trace_adj = adj
                    trace_starts = starts
                reachable_by_line_page[(str(line), page_no)] = reachable_nodes(trace_adj, trace_starts)

    for cu, sm in schedule_by_cu.items():
        expected = str(sm["mv_line_instance_key"])
        for tb in xfr_terminal_bindings.get(str(cu), []) or []:
            page_no = tb.get("page")
            nid = tb.get("graph_node_id")
            if page_no is None or nid is None:
                continue
            page_no = int(page_no); nid = int(nid)
            reached_lines = sorted({
                line for (line, pno), nodes in reachable_by_line_page.items()
                if pno == page_no and nid in nodes
            })
            if expected in reached_lines:
                operator_graph_verified.append({
                    "cu_instance_key": str(cu),
                    "mv_line_instance_key": expected,
                    "status": "GRAPH_VERIFIED",
                    "basis": "OPERATOR_CALIBRATED_SLD_STRUCTURAL_TOPOLOGY_TRACE",
                    "trace_semantics": "STRUCTURAL_TOPOLOGY__DEVICE_STATE_PRESERVED_SEPARATELY",
                    "interposed_device_topology_edge_count_on_page": len((augmented_pages.get(page_no) or {}).get("added_device_topology_edges", []) or []),
                    "page": page_no,
                    "graph_node_id": nid,
                    "terminal_binding": tb,
                    "reachable_line_ids": reached_lines,
                })
            elif reached_lines:
                operator_graph_conflicts.append({
                    "cu_instance_key": str(cu),
                    "schedule_mv_line": expected,
                    "graph_mv_lines": reached_lines,
                    "status": "CONFLICT",
                    "reason": "OPERATOR_CALIBRATED_SLD_GRAPH_DISAGREES_WITH_EXPLICIT_SCHEDULE",
                    "page": page_no,
                })

    # Merge positive graph evidence by CU/feeder pair. Existing layout-component
    # verification is preserved; operator-calibrated SLD traces add an independent
    # evidence channel rather than replacing it.
    gv_index = {(str(x["cu_instance_key"]), str(x["mv_line_instance_key"])): x for x in graph_verified}
    for row in operator_graph_verified:
        key = (str(row["cu_instance_key"]), str(row["mv_line_instance_key"]))
        if key not in gv_index:
            graph_verified.append(row); gv_index[key] = row
    graph_conflicts.extend(operator_graph_conflicts)

    by_line: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in schedule_membership:
        by_line[str(m["mv_line_instance_key"])].append(m)

    template = template_schedule_resolution or {}
    downstream_template_available = bool(
        (template.get("semantic_support", {}) or {}).get("inverter_template_supported")
        and template.get("inferred_target_counts", {}).get("STRING_BOX")
    )

    traces: List[Dict[str, Any]] = []
    verified_pairs = {(x["cu_instance_key"], x["mv_line_instance_key"]) for x in graph_verified}
    source_pairs = {(x["cu_instance_key"], x["mv_line_instance_key"]) for x in source_crosschecked}
    for line in sorted(by_line, key=lambda s: (int(re.search(r"(\d+)$", s).group(1)) if re.search(r"(\d+)$", s) else 10**9, s)):
        members = by_line[line]
        member_keys = [str(m["cu_instance_key"]) for m in members]
        gv = [c for c in member_keys if (c, line) in verified_pairs]
        sc = [c for c in member_keys if (c, line) in source_pairs]
        roots = line_roots.get(line, [])
        if len(gv) == len(member_keys) and member_keys:
            status = "GRAPH_VERIFIED"
        elif gv:
            status = "PARTIALLY_GRAPH_VERIFIED"
        elif sc:
            status = "SOURCE_CROSSCHECKED_NOT_GRAPH_VERIFIED"
        else:
            status = "MEMBERSHIP_SOURCE_EXPLICIT_TRACE_UNRESOLVED"
        suggested_breakpoints = _suggest_graph_breakpoints(
            line, reachable_by_line_page, augmented_pages,
            excluded_breakpoints=reviewed_breakpoint_keys,
            blocked_device_reviews=[*interposed_device_reviews, *non_electrical_graphic_reviews],
        )
        traces.append({
            "feeder_id": line,
            "trace_origin": root_semantics,
            "line_root_evidence": roots,
            "member_cu_instance_keys": member_keys,
            # Schedule rows establish membership, not electrical ordering.
            "electrical_order_status": "UNRESOLVED" if len(member_keys) > 1 else "TRIVIAL_SINGLE_MEMBER",
            "electrically_ordered_cu_instance_keys": member_keys if len(member_keys) <= 1 else [],
            "graph_verified_cu_instance_keys": gv,
            "source_crosschecked_cu_instance_keys": sc,
            "operator_terminal_bound_cu_instance_keys": [c for c in member_keys if c in xfr_terminal_bindings],
            "operator_bridge_count_on_relevant_pages": sum(
                len((augmented_pages.get(int(tb.get("page"))) or {}).get("added_bridges", []) or [])
                for c in member_keys for tb in (xfr_terminal_bindings.get(c, []) or []) if tb.get("page") is not None
            ),
            "downstream_target": "STRING_BOX_OR_LOW_VOLTAGE_DC_PANEL",
            "downstream_template_available": downstream_template_available,
            "end_to_end_graph_trace_complete": False,
            "suggested_breakpoints": suggested_breakpoints,
            "reviewed_breakpoints": [x for x in breakpoint_reviews if str(x.get("feeder_id") or "") == str(line)],
            "interposed_devices": [x for x in interposed_device_reviews if str(x.get("feeder_id") or "") == str(line)],
            "non_electrical_graphics": [x for x in non_electrical_graphic_reviews if str(x.get("feeder_id") or "") == str(line)],
            "status": status,
            "policy": "TRACE_FROM_HV_MV_SECONDARY_OR_MV_BUS_WHEN_REPRESENTED;_NEVER_TREAT_SCHEDULE_ROW_ORDER_AS_ELECTRICAL_ORDER",
        })

    # Only hard graph contradictions warrant a conflict request.  Missing graph
    # continuity is grouped by feeder so the operator can identify a breakpoint
    # or path segment rather than manually assigning every CU.
    unresolved_trace_feeders = [t for t in traces if t["status"] != "GRAPH_VERIFIED"]
    requests: List[Dict[str, Any]] = []
    if unresolved_trace_feeders and schedule_membership:
        requests.append({
            "request_id": f"{plant_id or 'PLANT'}::REQ::FEEDER_PATH_VERIFICATION",
            "target": "FEEDER_ELECTRICAL_PATH_VERIFICATION",
            "reason": "EXPLICIT_MEMBERSHIP_PRESENT_BUT_ELECTRICAL_PATH_NOT_FULLY_TRAVERSABLE",
            "interaction_mode": "VISUAL_SELECT_OR_CONFIRM_BREAKPOINT",
            "status": "OPEN",
            "required_for": "TOPOLOGY_VERIFICATION_NOT_MEMBERSHIP_COUNT",
            "context": {
                "plant_id": plant_id,
                "feeder_count": len(unresolved_trace_feeders),
                "feeders": [
                    {
                        "feeder_id": t["feeder_id"],
                        "member_cu_instance_keys": t["member_cu_instance_keys"],
                        "graph_verified_cu_instance_keys": t["graph_verified_cu_instance_keys"],
                        "status": t["status"],
                        "suggested_breakpoints": t.get("suggested_breakpoints", [])[:2],
                    }
                    for t in unresolved_trace_feeders
                ],
                "operator_goal": "Calibrate one representative XFR MV terminal and, only where needed, one conductive inline graph gap. Do not manually re-enter CU membership.",
                "recommended_actions": [
                    "BIND_FEEDER_ROOT_PATTERN",
                    "BIND_XFR_MV_TERMINAL_PATTERN",
                    "CLASSIFY_FEEDER_BREAKPOINT",
                    "ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN",
                ],
                "operator_safety_rule": "A suggested breakpoint must first be classified as conductive continuity, interposed electrical device, non-electrical graphic, or unresolved. Never bridge an interposed device, a non-electrical graphic, or transformer windings.",
            },
        })

    return {
        "plant_id": plant_id,
        "explicit_schedule_membership": schedule_membership,
        "explicit_schedule_conflicts": schedule_conflicts,
        "graph_verified_membership": graph_verified,
        "source_crosschecked_membership": source_crosschecked,
        "graph_conflicts": graph_conflicts,
        "feeder_traces": traces,
        "operator_graph_calibration": {
            "xfr_terminal_pattern_count": len(operator_patterns.get("xfr_terminal_patterns", [])),
            "feeder_root_pattern_count": len(operator_patterns.get("feeder_root_patterns", [])),
            "conductive_gap_bridge_pattern_count": len(operator_patterns.get("conductive_gap_bridge_patterns", [])),
            "explicit_graph_bridge_instance_count": len(operator_patterns.get("instance_bridges", [])),
            "xfr_terminal_bound_instance_count": len(xfr_terminal_bindings),
            "feeder_root_bound_count": sum(len(v) for v in operator_root_bindings.values()),
            "operator_calibrated_graph_verified_count": len(operator_graph_verified),
            "operator_calibrated_graph_conflict_count": len(operator_graph_conflicts),
            "added_bridge_count": sum(len(x.get("added_bridges", []) or []) for x in augmented_pages.values()),
            "added_instance_bridge_count": sum(len(x.get("added_instance_bridges", []) or []) for x in augmented_pages.values()),
            "added_pattern_bridge_count": sum(len(x.get("added_pattern_bridges", []) or []) for x in augmented_pages.values()),
            "modeled_interposed_device_count": sum(len(x.get("modeled_interposed_devices", []) or []) for x in augmented_pages.values()),
            "added_device_topology_edge_count": sum(len(x.get("added_device_topology_edges", []) or []) for x in augmented_pages.values()),
            "breakpoint_review_count": len(breakpoint_reviews),
            "breakpoint_continuity_confirmed_count": len(confirmed_continuity_reviews),
            "breakpoint_interposed_device_count": len(interposed_device_reviews),
            "breakpoint_non_electrical_graphic_count": len(non_electrical_graphic_reviews),
            "breakpoint_unresolved_count": len(unresolved_breakpoint_reviews),
            "excluded_non_electrical_graphic_node_count": sum(len(v) for v in blocked_graphic_nodes_by_line_page.values()),
            "interposed_devices": interposed_device_reviews,
            "non_electrical_graphics": non_electrical_graphic_reviews,
        },
        "resolution_requests": requests,
        "summary": {
            "explicit_schedule_membership_count": len(schedule_membership),
            "explicit_schedule_feeder_count": len(by_line),
            "explicit_schedule_conflict_count": len(schedule_conflicts),
            "sld_xfr_identity_crosschecked_count": len(source_crosschecked),
            "graph_verified_cu_mv_membership_count": len(graph_verified),
            "graph_conflict_count": len(graph_conflicts),
            "feeder_trace_count": len(traces),
            "fully_graph_verified_feeder_count": sum(t["status"] == "GRAPH_VERIFIED" for t in traces),
            "end_to_end_graph_trace_complete_count": sum(bool(t["end_to_end_graph_trace_complete"]) for t in traces),
            "operator_xfr_terminal_bound_instance_count": len(xfr_terminal_bindings),
            "operator_feeder_root_bound_count": sum(len(v) for v in operator_root_bindings.values()),
            "operator_calibrated_graph_verified_count": len(operator_graph_verified),
            "operator_added_bridge_count": sum(len(x.get("added_bridges", []) or []) for x in augmented_pages.values()),
            "operator_added_instance_bridge_count": sum(len(x.get("added_instance_bridges", []) or []) for x in augmented_pages.values()),
            "operator_modeled_interposed_device_count": sum(len(x.get("modeled_interposed_devices", []) or []) for x in augmented_pages.values()),
            "operator_added_device_topology_edge_count": sum(len(x.get("added_device_topology_edges", []) or []) for x in augmented_pages.values()),
            "breakpoint_review_count": len(breakpoint_reviews),
            "breakpoint_continuity_confirmed_count": len(confirmed_continuity_reviews),
            "breakpoint_interposed_device_count": len(interposed_device_reviews),
            "breakpoint_non_electrical_graphic_count": len(non_electrical_graphic_reviews),
            "breakpoint_unresolved_count": len(unresolved_breakpoint_reviews),
            "excluded_non_electrical_graphic_node_count": sum(len(v) for v in blocked_graphic_nodes_by_line_page.values()),
            "suggested_breakpoint_count": sum(len(t.get("suggested_breakpoints", []) or []) for t in traces),
        },
        "policy": "SOURCE_EXPLICIT_MEMBERSHIP_IS_SEPARATE_FROM_GRAPH_TOPOLOGY_VERIFICATION;_OPERATOR_ASSISTS_BREAKPOINTS_NOT_BULK_MEMBERSHIP_ENTRY",
    }


def apply_feeder_membership_to_layout_resolution(
    layout_resolution: Dict[str, Any],
    feeder_verification: Dict[str, Any],
) -> Dict[str, Any]:
    """Overlay explicit source membership without discarding legacy evidence."""
    out = layout_resolution
    explicit = list((feeder_verification or {}).get("explicit_schedule_membership", []) or [])
    if not explicit:
        # Keep all previous behavior bit-for-bit when this evidence is absent.
        out.setdefault("summary", {})["explicit_schedule_membership_count"] = 0
        out["summary"]["graph_verified_cu_mv_membership_count"] = int(
            (feeder_verification or {}).get("summary", {}).get("graph_verified_cu_mv_membership_count") or 0
        )
        return out

    legacy = list(out.get("cu_mv_membership", []) or [])
    legacy_by_cu: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for x in legacy:
        legacy_by_cu[str(x.get("cu_instance_key"))].append(x)

    merged: List[Dict[str, Any]] = []
    explicit_keys = set()
    weak_disagreements = []
    hard_disagreements = []
    graph_verified_pairs = {
        (str(x.get("cu_instance_key")), str(x.get("mv_line_instance_key")))
        for x in (feeder_verification or {}).get("graph_verified_membership", []) or []
    }
    graph_conflict_cus = {
        str(x.get("cu_instance_key")) for x in (feeder_verification or {}).get("graph_conflicts", []) or []
    }

    for x in explicit:
        cu = str(x.get("cu_instance_key"))
        line = str(x.get("mv_line_instance_key"))
        explicit_keys.add(cu)
        supporting = legacy_by_cu.get(cu, [])
        for old in supporting:
            if str(old.get("mv_line_instance_key")) == line:
                continue
            if old.get("basis") == "EXPLICIT_LINE_ID_PLUS_SHARED_GRAPH_COMPONENT":
                hard_disagreements.append({"cu_instance_key": cu, "schedule": line, "legacy": old})
            else:
                weak_disagreements.append({"cu_instance_key": cu, "schedule": line, "legacy": old})
        row = {k: v for k, v in x.items() if k != "schedule_row"}
        row["membership_source"] = "EXPLICIT_SOURCE_SCHEDULE"
        row["topology_verified"] = (cu, line) in graph_verified_pairs
        row["topology_verification_status"] = (
            "CONFLICT" if cu in graph_conflict_cus
            else "GRAPH_VERIFIED" if row["topology_verified"]
            else "NOT_FULLY_GRAPH_VERIFIED"
        )
        row["supporting_legacy_evidence"] = supporting
        merged.append(row)

    # Preserve old memberships for CUs not covered by explicit schedules.
    for old in legacy:
        if str(old.get("cu_instance_key")) not in explicit_keys:
            merged.append(old)

    merged.sort(key=lambda r: _sort_key(r.get("cu_instance_key")))
    out["cu_mv_membership"] = merged
    resolved_keys = {str(x.get("cu_instance_key")) for x in merged}
    out["unresolved_membership"] = [
        u for u in (out.get("unresolved_membership", []) or [])
        if str(u.get("cu_instance_key")) not in resolved_keys
    ]

    # Ensure feeder inventory contains every explicit schedule line, even if the
    # overview line label was not separately detected.
    line_keys = {str(x.get("instance_key")) for x in out.get("mv_lines", []) or [] if x.get("instance_key") is not None}
    schedule_rows_by_line: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for x in explicit:
        schedule_rows_by_line[str(x["mv_line_instance_key"])].append(x)
    for line, rows in schedule_rows_by_line.items():
        if line in line_keys:
            continue
        out.setdefault("mv_lines", []).append({
            "line_id": f"MV_LINE::{line}",
            "instance_key": line,
            "synthetic_line_key": None,
            "label_status": "RESOLVED",
            "source_status": "DETECTED",
            "representations": [
                {"page": r.get("page"), "doc": r.get("doc"), "text": f"{line} CIRCUIT SCHEDULE", "source_status": "DETECTED"}
                for r in rows[:1]
            ],
        })

    s = out.setdefault("summary", {})
    s["mv_line_count"] = len(out.get("mv_lines", []) or [])
    s["resolved_cu_mv_membership_count"] = len(merged)
    s["unresolved_cu_mv_membership_count"] = len(out.get("unresolved_membership", []) or [])
    s["explicit_schedule_membership_count"] = len(explicit)
    s["graph_verified_cu_mv_membership_count"] = int((feeder_verification or {}).get("summary", {}).get("graph_verified_cu_mv_membership_count") or 0)
    s["membership_hard_conflict_count"] = len(hard_disagreements)
    s["weak_geometry_disagreement_count"] = len(weak_disagreements)
    out["membership_diagnostics"] = {
        "hard_disagreements": hard_disagreements,
        "weak_geometry_disagreements": weak_disagreements,
    }
    return out
