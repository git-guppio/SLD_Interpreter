from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import networkx as nx

from .config import GeometryThresholds
from .models import (
    CrossingRecord,
    GraphEdge,
    GraphNode,
    Point,
    VectorSegment,
)


def _snap_value(v: float, tol: float) -> float:
    return round(v / tol) * tol


def _snap_point(p: Point, tol: float) -> Point:
    return (_snap_value(p[0], tol), _snap_value(p[1], tol))


def _point_distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_on_segment(
    p: Point,
    s: VectorSegment,
    tol: float,
    *,
    include_endpoints: bool = True,
) -> bool:
    x, y = p
    (x1, y1), (x2, y2) = s.p1, s.p2

    if s.orientation == "H":
        if abs(y - y1) > tol:
            return False
        lo, hi = sorted((x1, x2))
        if include_endpoints:
            return lo - tol <= x <= hi + tol
        return lo + tol < x < hi - tol

    if abs(x - x1) > tol:
        return False
    lo, hi = sorted((y1, y2))
    if include_endpoints:
        return lo - tol <= y <= hi + tol
    return lo + tol < y < hi - tol


def _orthogonal_intersection(
    h: VectorSegment,
    v: VectorSegment,
    tol: float,
) -> Tuple[bool, Point]:
    assert h.orientation == "H"
    assert v.orientation == "V"

    x = v.p1[0]
    y = h.p1[1]
    hx0, hx1 = sorted((h.p1[0], h.p2[0]))
    vy0, vy1 = sorted((v.p1[1], v.p2[1]))

    hit = (
        hx0 - tol <= x <= hx1 + tol
        and vy0 - tol <= y <= vy1 + tol
    )
    return hit, (x, y)


def _is_endpoint_of(p: Point, s: VectorSegment, tol: float) -> bool:
    return (
        _point_distance(p, s.p1) <= tol
        or _point_distance(p, s.p2) <= tol
    )


def _canonicalize_segments(
    segments: Sequence[VectorSegment],
    snap_tol: float,
) -> List[VectorSegment]:
    """
    Snap coordinates but preserve source IDs / provenance.
    """
    out: List[VectorSegment] = []
    for s in segments:
        p1 = _snap_point(s.p1, snap_tol)
        p2 = _snap_point(s.p2, snap_tol)

        if s.orientation == "H":
            y = (p1[1] + p2[1]) / 2.0
            x1, x2 = sorted((p1[0], p2[0]))
            p1, p2 = (x1, y), (x2, y)
        else:
            x = (p1[0] + p2[0]) / 2.0
            y1, y2 = sorted((p1[1], p2[1]))
            p1, p2 = (x, y1), (x, y2)

        length = _point_distance(p1, p2)
        if length <= snap_tol:
            continue

        out.append(
            VectorSegment(
                segment_id=s.segment_id,
                orientation=s.orientation,
                p1=p1,
                p2=p2,
                length_pt=length,
                color_name=s.color_name,
                rgb=s.rgb,
                stroke_width=s.stroke_width,
                drawing_index=s.drawing_index,
                source_item_index=s.source_item_index,
                is_near_black=s.is_near_black,
            )
        )
    return out


def _collinear_contact_points(
    a: VectorSegment,
    b: VectorSegment,
    tol: float,
) -> List[Point]:
    """
    Return endpoints that land on the other collinear segment.
    This lets overlapping/adjacent source fragments become a continuous graph
    without inventing mid-air joins.
    """
    if a.orientation != b.orientation:
        return []

    pts: List[Point] = []
    if a.orientation == "H":
        if abs(a.p1[1] - b.p1[1]) > tol:
            return []
    else:
        if abs(a.p1[0] - b.p1[0]) > tol:
            return []

    for p in (a.p1, a.p2):
        if _point_on_segment(p, b, tol, include_endpoints=True):
            pts.append(p)
    for p in (b.p1, b.p2):
        if _point_on_segment(p, a, tol, include_endpoints=True):
            pts.append(p)

    # Deduplicate by snapped coordinate.
    unique = []
    seen = set()
    for p in pts:
        k = (round(p[0] / tol), round(p[1] / tol))
        if k in seen:
            continue
        seen.add(k)
        unique.append(p)
    return unique



def build_electrical_planar_graph(
    segments: Sequence[VectorSegment],
    page_w: float,
    page_h: float,
    geom: GeometryThresholds,
) -> Dict[str, Any]:
    """
    Build a conductor graph with SLD-safe crossing semantics.

    Joining rules:
      1. shared / near-coincident endpoints -> connected;
      2. endpoint touching another segment body -> connected T-junction;
      3. collinear fragments touching/overlapping -> connected;
      4. H/V interior-interior crossing -> NOT electrically connected.

    Performance note:
    alpha1 uses axis-grouped collinear scans + an x-bucket index for H/V
    intersections. This avoids the dense all-pairs spatial grid that becomes
    expensive on large Central-Inverter drawings such as PV8.
    """
    t0 = time.perf_counter()

    snap_tol = max(
        geom.vector_snap_tol_min_pt,
        min(page_w, page_h) * geom.vector_snap_tol_ratio,
    )
    touch_tol = snap_tol * geom.intersection_tolerance_multiplier

    segs = _canonicalize_segments(segments, snap_tol)
    by_id = {s.segment_id: s for s in segs}

    split_points: Dict[int, List[Point]] = defaultdict(list)
    for s in segs:
        split_points[s.segment_id].extend([s.p1, s.p2])

    crossings: List[CrossingRecord] = []
    junction_points = set()
    tested_collinear_pairs = 0
    tested_orthogonal_pairs = 0

    # ------------------------------------------------------------------
    # 1) Collinear continuity / overlap
    # ------------------------------------------------------------------
    horizontal_by_axis: Dict[int, List[VectorSegment]] = defaultdict(list)
    vertical_by_axis: Dict[int, List[VectorSegment]] = defaultdict(list)

    for s in segs:
        if s.orientation == "H":
            key = int(round(s.p1[1] / touch_tol))
            horizontal_by_axis[key].append(s)
        else:
            key = int(round(s.p1[0] / touch_tol))
            vertical_by_axis[key].append(s)

    def process_collinear_group(group: List[VectorSegment], orientation: str) -> None:
        nonlocal tested_collinear_pairs
        if orientation == "H":
            group.sort(key=lambda s: (s.p1[0], s.p2[0]))
            start_coord = lambda s: min(s.p1[0], s.p2[0])
            end_coord = lambda s: max(s.p1[0], s.p2[0])
        else:
            group.sort(key=lambda s: (s.p1[1], s.p2[1]))
            start_coord = lambda s: min(s.p1[1], s.p2[1])
            end_coord = lambda s: max(s.p1[1], s.p2[1])

        for i, a in enumerate(group):
            a_end = end_coord(a)
            for j in range(i + 1, len(group)):
                b = group[j]
                if start_coord(b) > a_end + touch_tol:
                    break
                tested_collinear_pairs += 1
                for p in _collinear_contact_points(a, b, touch_tol):
                    sp = _snap_point(p, snap_tol)
                    split_points[a.segment_id].append(sp)
                    split_points[b.segment_id].append(sp)
                    junction_points.add(sp)

    for group in horizontal_by_axis.values():
        process_collinear_group(group, "H")
    for group in vertical_by_axis.values():
        process_collinear_group(group, "V")

    # ------------------------------------------------------------------
    # 2) Orthogonal intersections
    #
    # Vertical segments have one x-coordinate, so index them by x bucket.
    # For each H segment query only x buckets covered by its x-range.
    # ------------------------------------------------------------------
    verticals = [s for s in segs if s.orientation == "V"]
    horizontals = [s for s in segs if s.orientation == "H"]

    x_bucket_width = max(
        24.0,
        min(page_w, page_h) * 0.0125,
        touch_tol * 8.0,
    )
    vertical_x_index: Dict[int, List[VectorSegment]] = defaultdict(list)

    for v in verticals:
        bx = int(math.floor(v.p1[0] / x_bucket_width))
        vertical_x_index[bx].append(v)

    for h in horizontals:
        hx0, hx1 = sorted((h.p1[0], h.p2[0]))
        b0 = int(math.floor((hx0 - touch_tol) / x_bucket_width))
        b1 = int(math.floor((hx1 + touch_tol) / x_bucket_width))

        seen_v = set()
        for bx in range(b0, b1 + 1):
            for v in vertical_x_index.get(bx, []):
                if v.segment_id in seen_v:
                    continue
                seen_v.add(v.segment_id)
                tested_orthogonal_pairs += 1

                hit, p = _orthogonal_intersection(h, v, touch_tol)
                if not hit:
                    continue
                p = _snap_point(p, snap_tol)

                h_end = _is_endpoint_of(p, h, touch_tol)
                v_end = _is_endpoint_of(p, v, touch_tol)

                if h_end or v_end:
                    split_points[h.segment_id].append(p)
                    split_points[v.segment_id].append(p)
                    junction_points.add(p)
                else:
                    crossings.append(
                        CrossingRecord(
                            point=p,
                            horizontal_segment_ids=[h.segment_id],
                            vertical_segment_ids=[v.segment_id],
                            electrical_join=False,
                        )
                    )

    # ------------------------------------------------------------------
    # 3) Split source conductors and build graph
    # ------------------------------------------------------------------
    G = nx.Graph()
    node_key_to_id: Dict[Tuple[int, int], int] = {}
    node_positions: Dict[int, Point] = {}
    edges: List[GraphEdge] = []

    def node_id(p: Point) -> int:
        p = _snap_point(p, snap_tol)
        key = (
            int(round(p[0] / snap_tol)),
            int(round(p[1] / snap_tol)),
        )
        if key not in node_key_to_id:
            nid = len(node_key_to_id)
            node_key_to_id[key] = nid
            node_positions[nid] = p
            G.add_node(nid)
        return node_key_to_id[key]

    edge_key_to_index: Dict[Tuple[int, int], int] = {}

    for s in segs:
        pts = [
            _snap_point(p, snap_tol)
            for p in split_points[s.segment_id]
            if _point_on_segment(p, s, touch_tol, include_endpoints=True)
        ]

        if s.orientation == "H":
            pts.sort(key=lambda p: p[0])
        else:
            pts.sort(key=lambda p: p[1])

        uniq = []
        seen = set()
        for p in pts:
            k = (
                int(round(p[0] / snap_tol)),
                int(round(p[1] / snap_tol)),
            )
            if k in seen:
                continue
            seen.add(k)
            uniq.append(p)

        for i in range(len(uniq) - 1):
            p1, p2 = uniq[i], uniq[i + 1]
            length = _point_distance(p1, p2)
            if length <= touch_tol:
                continue

            u, v = node_id(p1), node_id(p2)
            if u == v:
                continue
            key = (min(u, v), max(u, v))

            if key in edge_key_to_index:
                e = edges[edge_key_to_index[key]]
                if s.segment_id not in e.source_segment_ids:
                    e.source_segment_ids.append(s.segment_id)
                if s.color_name not in e.color_names:
                    e.color_names.append(s.color_name)
                if (
                    s.stroke_width is not None
                    and s.stroke_width not in e.stroke_widths
                ):
                    e.stroke_widths.append(s.stroke_width)
                continue

            eid = len(edges)
            e = GraphEdge(
                edge_id=eid,
                source=u,
                target=v,
                p1=p1,
                p2=p2,
                length_pt=length,
                orientation=s.orientation,
                source_segment_ids=[s.segment_id],
                color_names=[s.color_name],
                stroke_widths=(
                    [s.stroke_width] if s.stroke_width is not None else []
                ),
            )
            edge_key_to_index[key] = eid
            edges.append(e)
            G.add_edge(u, v, edge_id=eid, length_pt=length)

    # ------------------------------------------------------------------
    # 4) Junction classification
    # ------------------------------------------------------------------
    graph_nodes: List[GraphNode] = []
    node_type_counts = Counter()

    for nid in G.nodes():
        degree = int(G.degree(nid))
        p = node_positions[nid]
        incident = [
            int(G.edges[nid, nb]["edge_id"])
            for nb in G.neighbors(nid)
        ]

        if degree == 0:
            node_type = "ISOLATED"
        elif degree == 1:
            node_type = "ENDPOINT"
        elif degree == 2:
            nbs = list(G.neighbors(nid))
            p1 = node_positions[nbs[0]]
            p2 = node_positions[nbs[1]]
            v1 = (p1[0] - p[0], p1[1] - p[1])
            v2 = (p2[0] - p[0], p2[1] - p[1])
            same_vertical = (
                abs(v1[0]) <= touch_tol and abs(v2[0]) <= touch_tol
            )
            same_horizontal = (
                abs(v1[1]) <= touch_tol and abs(v2[1]) <= touch_tol
            )
            node_type = (
                "STRAIGHT"
                if same_vertical or same_horizontal
                else "CORNER"
            )
        elif degree == 3:
            node_type = "T_JUNCTION"
        else:
            node_type = "MULTI_JUNCTION"

        node_type_counts[node_type] += 1
        graph_nodes.append(
            GraphNode(
                node_id=nid,
                point=p,
                node_type=node_type,
                degree=degree,
                incident_edge_ids=incident,
                evidence={
                    "source_visible_junction": p in junction_points,
                },
            )
        )

    component_count = (
        nx.number_connected_components(G)
        if G.number_of_nodes()
        else 0
    )

    component_summaries = []
    for cid, comp_nodes in enumerate(nx.connected_components(G)):
        comp_nodes = set(comp_nodes)
        comp_edges = [
            e for e in edges
            if e.source in comp_nodes and e.target in comp_nodes
        ]
        if not comp_edges:
            continue

        xs = [node_positions[n][0] for n in comp_nodes]
        ys = [node_positions[n][1] for n in comp_nodes]
        component_summaries.append(
            {
                "component_id": cid,
                "node_count": len(comp_nodes),
                "edge_count": len(comp_edges),
                "total_length_pt": round(
                    sum(e.length_pt for e in comp_edges), 3
                ),
                "bbox": [
                    round(min(xs), 3),
                    round(min(ys), 3),
                    round(max(xs), 3),
                    round(max(ys), 3),
                ],
                "endpoint_count": sum(
                    1 for n in comp_nodes if G.degree(n) == 1
                ),
            }
        )

    return {
        "graph": G,
        "nodes": graph_nodes,
        "edges": edges,
        "crossings": crossings,
        "node_positions": node_positions,
        "node_type_counts": dict(node_type_counts),
        "connected_component_count": component_count,
        "component_summaries": component_summaries,
        "snap_tolerance_pt": round(snap_tol, 4),
        "touch_tolerance_pt": round(touch_tol, 4),
        "source_segment_count": len(segments),
        "canonical_segment_count": len(segs),
        "tested_collinear_pairs": tested_collinear_pairs,
        "tested_orthogonal_pairs": tested_orthogonal_pairs,
        "processing_seconds": round(time.perf_counter() - t0, 4),
    }
