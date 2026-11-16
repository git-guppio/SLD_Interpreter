from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pymupdf as fitz

from .config import GeometryThresholds
from .models import (
    BBox,
    GraphNode,
    Point,
    SymbolCandidate,
    TerminalBinding,
    TextEquipmentAnchor,
)


def _center(b: BBox) -> Point:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _bbox_diag(b: BBox) -> float:
    return math.hypot(b[2] - b[0], b[3] - b[1])


def _bbox_distance(a: BBox, b: BBox) -> float:
    dx = max(0.0, max(a[0] - b[2], b[0] - a[2]))
    dy = max(0.0, max(a[1] - b[3], b[1] - a[3]))
    return math.hypot(dx, dy)


def _is_near_black(color: Any, max_channel: float) -> bool:
    if color is None:
        return False
    try:
        rgb = tuple(float(v) for v in color[:3])
        return max(rgb) <= max_channel
    except Exception:
        return False


def _line_points(item: Any) -> Optional[Tuple[Point, Point]]:
    if not item or item[0] != "l":
        return None
    a, b = item[1], item[2]
    return ((float(a.x), float(a.y)), (float(b.x), float(b.y)))


def _looks_like_closed_rect(
    drawing: Dict[str, Any],
    bbox: BBox,
    tol: float,
) -> bool:
    """
    Detect an axis-aligned enclosure from either a native rectangle or line
    primitives covering all four sides.
    """
    items = drawing.get("items", [])
    if any(it and it[0] == "re" for it in items):
        return True

    x0, y0, x1, y1 = bbox
    top = bottom = left = right = False

    for it in items:
        pts = _line_points(it)
        if pts is None:
            continue
        (ax, ay), (bx, by) = pts
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


def _circle_like_drawing(
    drawing: Dict[str, Any],
    min_size: float,
) -> Optional[Tuple[BBox, float]]:
    """
    PyMuPDF commonly represents a vector circle as four cubic Bézier curves.
    """
    r = drawing.get("rect")
    if r is None:
        return None
    w, h = float(r.width), float(r.height)
    if min(w, h) < min_size:
        return None
    if max(w, h) / max(min(w, h), 1e-9) > 1.18:
        return None

    kinds = [it[0] for it in drawing.get("items", []) if it]
    if len(kinds) != 4 or any(k != "c" for k in kinds):
        return None

    b = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
    return b, (w + h) / 4.0


def _has_internal_diagonal(
    bbox: BBox,
    nonorth_lines: Sequence[Tuple[Point, Point]],
    tol: float,
) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return False

    ex = tol * 2.0
    for a, b in nonorth_lines:
        if not (
            x0 - ex <= a[0] <= x1 + ex
            and y0 - ex <= a[1] <= y1 + ex
            and x0 - ex <= b[0] <= x1 + ex
            and y0 - ex <= b[1] <= y1 + ex
        ):
            continue
        dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
        if dx >= 0.45 * w and dy >= 0.45 * h:
            return True
    return False


def _terminal_side(p: Point, bbox: BBox) -> str:
    x, y = p
    x0, y0, x1, y1 = bbox
    d = {
        "LEFT": abs(x - x0),
        "RIGHT": abs(x - x1),
        "TOP": abs(y - y0),
        "BOTTOM": abs(y - y1),
    }
    return min(d, key=d.get)


def _distance_to_bbox_border(p: Point, bbox: BBox) -> float:
    x, y = p
    x0, y0, x1, y1 = bbox

    if x0 <= x <= x1 and y0 <= y <= y1:
        return min(abs(x - x0), abs(x - x1), abs(y - y0), abs(y - y1))

    dx = max(x0 - x, 0.0, x - x1)
    dy = max(y0 - y, 0.0, y - y1)
    return math.hypot(dx, dy)


def bind_graph_terminals(
    symbol: SymbolCandidate,
    graph_nodes: Sequence[GraphNode],
    search_radius: float,
    max_terminal_count: int,
) -> List[TerminalBinding]:
    """
    Bind conductor-graph nodes to a geometry candidate boundary.

    Only graph nodes close to the symbol perimeter are considered. Nodes deep
    inside the bbox are not terminals.
    """
    raw = []
    x0, y0, x1, y1 = symbol.bbox
    for node in graph_nodes:
        x, y = node.point
        if not (
            x0 - search_radius <= x <= x1 + search_radius
            and y0 - search_radius <= y <= y1 + search_radius
        ):
            continue

        d = _distance_to_bbox_border(node.point, symbol.bbox)
        if d > search_radius:
            continue

        # reject points deep inside the symbol body
        if (
            x0 + search_radius < x < x1 - search_radius
            and y0 + search_radius < y < y1 - search_radius
        ):
            continue

        raw.append((d, node))

    raw.sort(key=lambda x: (x[0], x[1].node_id))

    # spatial dedupe
    kept = []
    for d, node in raw:
        if any(
            math.hypot(
                node.point[0] - other.point[0],
                node.point[1] - other.point[1],
            ) <= max(1.0, search_radius * 0.35)
            for _, other in kept
        ):
            continue
        kept.append((d, node))

    if len(kept) > max_terminal_count:
        return []

    out = []
    for i, (d, node) in enumerate(kept, start=1):
        conf = max(0.45, min(0.98, 1.0 - d / max(search_radius, 1e-9)))
        out.append(
            TerminalBinding(
                terminal_id=f"{symbol.symbol_id}_T{i:02d}",
                graph_node_id=node.node_id,
                point=node.point,
                side=_terminal_side(node.point, symbol.bbox),
                distance_to_symbol_border_pt=round(d, 3),
                confidence=round(conf, 3),
                evidence={
                    "graph_node_type": node.node_type,
                    "graph_node_degree": node.degree,
                },
            )
        )
    return out


def detect_vector_symbol_candidates(
    page: fitz.Page,
    page_no: int,
    doc_id: str,
    graph_nodes: Sequence[GraphNode],
    geom: GeometryThresholds,
) -> List[SymbolCandidate]:
    """
    Geometry candidate generator for the Central-Inverter pipeline.

    alpha2 deliberately recognizes only strong geometric families:
      - paired circle-like transformer candidates;
      - closed rectangular electrical enclosures;
      - rectangle + diagonal => central-inverter candidate.

    A generic rectangle is retained only when the conductor graph reaches its
    boundary. This removes most text-glyph / drafting boxes.
    """
    drawings = page.get_drawings()
    min_dim = min(float(page.mediabox.width), float(page.mediabox.height))
    max_bbox = max(geom.symbol_min_bbox_pt * 2.0, min_dim * geom.symbol_max_bbox_ratio)
    terminal_radius = max(
        geom.symbol_terminal_search_radius_min_pt,
        min_dim * geom.symbol_terminal_search_radius_ratio,
    )
    rect_tol = max(0.8, terminal_radius * 0.25)

    # Collect non-orthogonal line primitives once for diagonal evidence.
    nonorth_lines: List[Tuple[Point, Point]] = []
    for d in drawings:
        if not _is_near_black(d.get("color"), geom.near_black_max_channel):
            continue
        for it in d.get("items", []):
            pts = _line_points(it)
            if pts is None:
                continue
            a, b = pts
            dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
            if dx > rect_tol and dy > rect_tol:
                nonorth_lines.append((a, b))

    raw_candidates: List[SymbolCandidate] = []
    seq = 0

    # Closed enclosures.
    for d_idx, d in enumerate(drawings):
        if len(raw_candidates) >= geom.symbol_candidate_cap:
            break
        if not _is_near_black(d.get("color"), geom.near_black_max_channel):
            continue
        r = d.get("rect")
        if r is None:
            continue

        w, h = float(r.width), float(r.height)
        if min(w, h) < geom.symbol_min_bbox_pt:
            continue
        if max(w, h) > max_bbox:
            continue
        aspect = w / max(h, 1e-9)
        if not (
            geom.symbol_rect_aspect_min <= aspect
            <= geom.symbol_rect_aspect_max
        ):
            continue

        bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
        if not _looks_like_closed_rect(d, bbox, rect_tol):
            continue

        seq += 1
        has_diag = _has_internal_diagonal(bbox, nonorth_lines, rect_tol)
        candidate_type = (
            "CENTRAL_INVERTER_CANDIDATE"
            if has_diag else "ELECTRICAL_ENCLOSURE_CANDIDATE"
        )
        conf = 0.78 if has_diag else 0.55

        cand = SymbolCandidate(
            symbol_id=f"{doc_id}_P{page_no:03d}_VEC_{seq:04d}",
            candidate_type=candidate_type,
            bbox=bbox,
            center=_center(bbox),
            page=page_no,
            doc=doc_id,
            confidence=conf,
            evidence_state="GEOMETRY_ONLY",
            geometry_kind="RECTANGLE_WITH_DIAGONAL" if has_diag else "CLOSED_RECTANGLE",
            evidence={
                "drawing_index": d_idx,
                "aspect_ratio": round(aspect, 4),
                "has_internal_diagonal": has_diag,
            },
        )
        cand.terminals = bind_graph_terminals(
            cand, graph_nodes, terminal_radius, geom.symbol_max_terminal_count
        )

        # A geometry shape becomes a SYMBOL candidate only when the conductor
        # graph reaches its boundary. An isolated rectangle/diagonal remains
        # drafting geometry, not an electrical symbol candidate.
        if not cand.terminals:
            continue

        raw_candidates.append(cand)

    # Circle-pair transformers.
    circles = []
    for d_idx, d in enumerate(drawings):
        if not _is_near_black(d.get("color"), geom.near_black_max_channel):
            continue
        c = _circle_like_drawing(d, max(0.4, geom.symbol_min_bbox_pt * 0.25))
        if c is None:
            continue
        bbox, radius = c
        circles.append((d_idx, bbox, radius, _center(bbox)))

    # Spatial bucket by approximate centre.
    if circles:
        median_diam = sorted([2 * c[2] for c in circles])[len(circles)//2]
        cell = max(2.0, median_diam * 2.5)
        buckets: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for i, (_, _, _, c) in enumerate(circles):
            buckets[(int(c[0] // cell), int(c[1] // cell))].append(i)

        used_pairs = set()
        for i, (di, bi, ri, ci) in enumerate(circles):
            bx, by = int(ci[0] // cell), int(ci[1] // cell)
            for gx in range(bx - 1, bx + 2):
                for gy in range(by - 1, by + 2):
                    for j in buckets.get((gx, gy), []):
                        if j <= i:
                            continue
                        dj, bj, rj, cj = circles[j]
                        size_ratio = max(ri, rj) / max(min(ri, rj), 1e-9)
                        if size_ratio > 1.25:
                            continue
                        dist = math.hypot(ci[0] - cj[0], ci[1] - cj[1])
                        mean_d = ri + rj
                        if not (0.55 * mean_d <= dist <= 1.60 * mean_d):
                            continue
                        pair = (i, j)
                        if pair in used_pairs:
                            continue
                        used_pairs.add(pair)

                        bbox = (
                            min(bi[0], bj[0]), min(bi[1], bj[1]),
                            max(bi[2], bj[2]), max(bi[3], bj[3]),
                        )
                        seq += 1
                        cand = SymbolCandidate(
                            symbol_id=f"{doc_id}_P{page_no:03d}_VEC_{seq:04d}",
                            candidate_type="PAIRED_CIRCLE_ELECTRICAL_CANDIDATE",
                            bbox=bbox,
                            center=_center(bbox),
                            page=page_no,
                            doc=doc_id,
                            confidence=0.82,
                            evidence_state="GEOMETRY_ONLY",
                            geometry_kind="PAIRED_CIRCLE_LIKE_PATHS",
                            evidence={
                                "drawing_indices": [di, dj],
                                "circle_size_ratio": round(size_ratio, 4),
                                "circle_center_distance_pt": round(dist, 3),
                            },
                        )
                        cand.terminals = bind_graph_terminals(
                            cand, graph_nodes, terminal_radius,
                            geom.symbol_max_terminal_count,
                        )
                        # Paired circles are common in drafting. They become
                        # transformer symbol candidates only when the planar
                        # conductor graph reaches the pair boundary.
                        if not cand.terminals:
                            continue
                        raw_candidates.append(cand)

    # deterministic geometry dedupe by type and rounded bbox
    seen = set()
    deduped = []

    for c in raw_candidates:
        key = (
            c.candidate_type,
            tuple(round(v, 1) for v in c.bbox),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    # Consolidate near-overlapping transformer candidates.
    #
    # A single transformer symbol may contain multiple circle-like paths.
    # Pairwise circle detection can therefore generate several candidates
    # for the same physical symbol. Those candidates must be merged before
    # terminal tracing, otherwise zero-length false relations are created.
    out = []
    used = set()

    for i, cand in enumerate(deduped):

        if i in used:
            continue

        if cand.candidate_type != "PAIRED_CIRCLE_ELECTRICAL_CANDIDATE":
            used.add(i)
            out.append(cand)
            continue

        cluster = [i]

        changed = True
        while changed:
            changed = False

            for j, other in enumerate(deduped):

                if j in used or j in cluster:
                    continue

                if other.candidate_type != "PAIRED_CIRCLE_ELECTRICAL_CANDIDATE":
                    continue

                for k in cluster:
                    ref = deduped[k]

                    center_distance = math.hypot(
                        other.center[0] - ref.center[0],
                        other.center[1] - ref.center[1],
                    )

                    scale = max(
                        _bbox_diag(other.bbox),
                        _bbox_diag(ref.bbox),
                    )

                    if center_distance <= 0.40 * scale:
                        cluster.append(j)
                        changed = True
                        break

        for k in cluster:
            used.add(k)

        if len(cluster) == 1:
            out.append(cand)
            continue

        members = [deduped[k] for k in cluster]

        merged_bbox = (
            min(m.bbox[0] for m in members),
            min(m.bbox[1] for m in members),
            max(m.bbox[2] for m in members),
            max(m.bbox[3] for m in members),
        )

        cand.bbox = merged_bbox
        cand.center = _center(merged_bbox)
        cand.geometry_kind = "PAIRED_CIRCLE_CLUSTER"

        cand.evidence["consolidated_candidate_count"] = len(members)
        cand.evidence["consolidated_candidate_ids"] = [
            m.symbol_id for m in members
        ]

        # Re-bind terminals on the consolidated physical symbol.
        merged_terminals = bind_graph_terminals(
            cand,
            graph_nodes,
            terminal_radius,
            geom.symbol_max_terminal_count,
        )

        if merged_terminals:
            cand.terminals = merged_terminals

        out.append(cand)

    return out

def _compatible(anchor_type: str, candidate_type: str) -> bool:
    if anchor_type == "CENTRAL_INVERTER":
        return candidate_type in {
            "CENTRAL_INVERTER_CANDIDATE",
            "ELECTRICAL_ENCLOSURE_CANDIDATE",
        }

    if anchor_type in {"MV_LV_TRANSFORMER", "TRANSFORMER_CANDIDATE"}:
        return candidate_type == "PAIRED_CIRCLE_ELECTRICAL_CANDIDATE"

    if anchor_type in {"STRING_BOX", "DC_DISTRIBUTION_CANDIDATE"}:
        return candidate_type in {
            "ELECTRICAL_ENCLOSURE_CANDIDATE",
            "CENTRAL_INVERTER_CANDIDATE",
        }

    if anchor_type == "CONVERSION_UNIT":
        return candidate_type == "ELECTRICAL_ENCLOSURE_CANDIDATE"

    return False


def fuse_text_and_vector_candidates(
    vector_candidates: List[SymbolCandidate],
    text_anchors: List[TextEquipmentAnchor],
    page_w: float,
    page_h: float,
    geom: GeometryThresholds,
) -> List[SymbolCandidate]:
    """
    One-to-one greedy fusion with strict compatibility. This is not yet the CU
    optimal matching backlog item; it is only text<->symbol candidate fusion.
    """
    max_dist = max(
        geom.symbol_text_fusion_distance_min_pt,
        min(page_w, page_h) * geom.symbol_text_fusion_distance_ratio,
    )

    used_vectors = set()
    fused: List[SymbolCandidate] = []

    for anchor in sorted(
        text_anchors,
        key=lambda a: (-a.confidence, a.anchor_id),
    ):
        # Only anchors identifying an instance or an explicit tag
        # may participate in text <-> geometry fusion.
        # FAMILY and CARDINALITY remain semantic evidence only.
        if anchor.anchor_role not in {"INSTANCE", "TAG"}:
            continue

        matches = []

        for i, cand in enumerate(vector_candidates):
            if i in used_vectors:
                continue
            if not _compatible(anchor.equipment_type, cand.candidate_type):
                continue
            d = _bbox_distance(anchor.bbox, cand.bbox)
            if d <= max_dist:
                matches.append((d, -cand.confidence, i, cand))

        if matches:
            matches.sort()
            d, _, i, cand = matches[0]
            used_vectors.add(i)

            # Type comes from explicit source text, geometry remains evidence.
            cand.candidate_type = anchor.equipment_type
            cand.evidence_state = "FUSED"
            cand.text_anchor_id = anchor.anchor_id
            cand.tag = anchor.tag
            cand.confidence = round(
                min(0.995, 0.55 * anchor.confidence + 0.45 * cand.confidence),
                3,
            )
            cand.evidence["text_fusion_distance_pt"] = round(d, 3)
            cand.evidence["text_evidence_kind"] = anchor.evidence_kind
            cand.evidence["text_source"] = anchor.source
            fused.append(cand)
        else:
            # Keep unbound source evidence; do not invent a symbol bbox.
            fused.append(
                SymbolCandidate(
                    symbol_id=anchor.anchor_id.replace("_TXT_", "_TEXTSYM_"),
                    candidate_type=anchor.equipment_type,
                    bbox=anchor.bbox,
                    center=_center(anchor.bbox),
                    page=anchor.page,
                    doc=anchor.doc,
                    confidence=anchor.confidence,
                    evidence_state="TEXT_ONLY",
                    text_anchor_id=anchor.anchor_id,
                    tag=anchor.tag,
                    terminals=[],
                    evidence={
                        "text_evidence_kind": anchor.evidence_kind,
                        "text_source": anchor.source,
                        "symbol_geometry_status": "NOT_BOUND",
                    },
                )
            )

    for i, cand in enumerate(vector_candidates):
        if i not in used_vectors:
            fused.append(cand)

    return fused
