from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import networkx as nx

from .config import GeometryThresholds
from .models import (
    GraphEdge,
    GraphNode,
    SymbolCandidate,
    TerminalBinding,
    TracedRelationCandidate,
)


DOMAIN_TYPES = {
    "CONVERSION_UNIT",
    "MV_LV_TRANSFORMER",
    "TRANSFORMER_CANDIDATE",
    "CENTRAL_INVERTER",
    "STRING_BOX",
    "DC_DISTRIBUTION_CANDIDATE",
}

HIGH_SPECIFICITY_GEOMETRY_TYPES = {
    "CENTRAL_INVERTER_CANDIDATE",
    "PAIRED_CIRCLE_ELECTRICAL_CANDIDATE",
}


def is_trace_eligible(symbol: SymbolCandidate) -> bool:
    """
    alpha3 only traces candidates that have graph-bound terminals AND either:
      - source text typed them into the Central-Inverter domain; or
      - geometry is high-specificity (inverter / transformer).
    Generic geometry-only enclosures are intentionally excluded.
    """
    if symbol.candidate_type.startswith("REJECTED_") or symbol.evidence.get("scale_status") == "OUTLIER":
        return False
    if not symbol.terminals:
        return False
    if symbol.candidate_type in DOMAIN_TYPES:
        return True
    if symbol.candidate_type in HIGH_SPECIFICITY_GEOMETRY_TYPES:
        return True
    return False


def _point_inside_bbox(
    point: Tuple[float, float],
    bbox: Tuple[float, float, float, float],
    margin: float = 0.0,
    strict: bool = False,
) -> bool:
    x, y = point
    x0, y0, x1, y1 = bbox
    if strict:
        return (
            x0 + margin < x < x1 - margin
            and y0 + margin < y < y1 - margin
        )
    return (
        x0 - margin <= x <= x1 + margin
        and y0 - margin <= y <= y1 + margin
    )


def _edge_is_internal_to_symbol(
    edge: GraphEdge,
    symbol: SymbolCandidate,
    margin: float,
) -> bool:
    """
    Remove symbol-internal/border drawing edges from the tracing graph.

    External conductors ending at a bound terminal are preserved. An edge is
    blocked when both endpoints live inside/on the same symbol enclosure, or
    when its midpoint lies strictly inside the symbol.
    """
    p1, p2 = edge.p1, edge.p2
    in1 = _point_inside_bbox(p1, symbol.bbox, margin=margin, strict=False)
    in2 = _point_inside_bbox(p2, symbol.bbox, margin=margin, strict=False)

    if in1 and in2:
        return True

    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    if _point_inside_bbox(mid, symbol.bbox, margin=0.0, strict=True):
        return True

    return False


def build_external_tracing_graph(
    graph_nodes: Sequence[GraphNode],
    graph_edges: Sequence[GraphEdge],
    symbols: Sequence[SymbolCandidate],
    geom: GeometryThresholds,
) -> Tuple[nx.Graph, Dict[str, Any]]:
    """
    Build a tracing graph from the planar conductor graph while blocking
    traversal through recognized symbol bodies.

    This is essential: symbol drawing primitives can otherwise short-circuit
    two external terminals through the geometry of the equipment itself.
    """
    eligible = [s for s in symbols if is_trace_eligible(s)]

    G = nx.Graph()
    for node in graph_nodes:
        G.add_node(
            node.node_id,
            point=node.point,
            node_type=node.node_type,
            degree=node.degree,
        )

    blocked_edge_ids: List[int] = []

    for edge in graph_edges:
        blocked_by = None
        for sym in eligible:
            if _edge_is_internal_to_symbol(
                edge,
                sym,
                geom.trace_symbol_interior_margin_pt,
            ):
                blocked_by = sym.symbol_id
                break

        if blocked_by is not None:
            blocked_edge_ids.append(edge.edge_id)
            continue

        G.add_edge(
            edge.source,
            edge.target,
            edge_id=edge.edge_id,
            length_pt=edge.length_pt,
        )

    return G, {
        "trace_eligible_symbol_count": len(eligible),
        "blocked_internal_edge_count": len(blocked_edge_ids),
        "blocked_internal_edge_ids": blocked_edge_ids,
    }


def _terminal_maps(
    symbols: Sequence[SymbolCandidate],
) -> Tuple[
    Dict[int, List[Tuple[str, TerminalBinding]]],
    Dict[str, SymbolCandidate],
]:
    by_node: Dict[int, List[Tuple[str, TerminalBinding]]] = defaultdict(list)
    by_symbol = {}

    for sym in symbols:
        if not is_trace_eligible(sym):
            continue
        by_symbol[sym.symbol_id] = sym
        for terminal in sym.terminals:
            by_node[int(terminal.graph_node_id)].append(
                (sym.symbol_id, terminal)
            )

    return by_node, by_symbol


def _confidence(
    source: SymbolCandidate,
    target: SymbolCandidate,
    src_terminal: TerminalBinding,
    tgt_terminal: TerminalBinding,
    branch_count: int,
    path_length: float,
    max_path_length: float,
) -> float:
    evidence = (
        source.confidence
        + target.confidence
        + src_terminal.confidence
        + tgt_terminal.confidence
    ) / 4.0

    path_factor = max(
        0.60,
        1.0 - 0.25 * (path_length / max(max_path_length, 1e-9)),
    )
    branch_factor = max(0.70, 1.0 - 0.03 * branch_count)
    return round(
        max(0.35, min(0.99, evidence * path_factor * branch_factor)),
        3,
    )


def trace_terminal_to_terminal(
    graph_nodes: Sequence[GraphNode],
    graph_edges: Sequence[GraphEdge],
    symbols: Sequence[SymbolCandidate],
    page_no: int,
    doc_id: str,
    page_w: float,
    page_h: float,
    geom: GeometryThresholds,
) -> Dict[str, Any]:
    """
    Trace topological neighbours between eligible symbol terminals.

    Search rule:
      - start from each source terminal;
      - traverse only the external conductor graph;
      - when a terminal of another eligible symbol is reached, record it and
        DO NOT traverse through that symbol terminal;
      - retain the shortest path per symbol pair;
      - relation remains undirected / direction unresolved in alpha3.

    This produces real graph-connectivity candidates, not proximity relations.
    """
    tracing_graph, graph_meta = build_external_tracing_graph(
        graph_nodes,
        graph_edges,
        symbols,
        geom,
    )

    terminal_by_node, symbol_by_id = _terminal_maps(symbols)
    node_by_id = {n.node_id: n for n in graph_nodes}

    max_path_length = max(
        geom.trace_max_path_length_min_pt,
        min(page_w, page_h) * geom.trace_max_path_length_ratio,
    )

    best_by_pair: Dict[
        Tuple[str, str],
        Tuple[
            float,
            SymbolCandidate,
            SymbolCandidate,
            TerminalBinding,
            TerminalBinding,
            List[int],
        ],
    ] = {}

    # Run bounded Dijkstra independently from each eligible source terminal.
    for src_node, src_bindings in terminal_by_node.items():
        if src_node not in tracing_graph:
            continue

        for src_symbol_id, src_terminal in src_bindings:
            src_symbol = symbol_by_id[src_symbol_id]

            heap: List[Tuple[float, int, List[int]]] = [
                (0.0, int(src_node), [int(src_node)])
            ]
            best_distance: Dict[int, float] = {int(src_node): 0.0}

            while heap:
                distance, node_id, path = heapq.heappop(heap)
                if distance > max_path_length:
                    break
                if distance > best_distance.get(node_id, float("inf")) + 1e-9:
                    continue

                foreign_bindings = [
                    (sid, term)
                    for sid, term in terminal_by_node.get(node_id, [])
                    if sid != src_symbol_id
                ]

                if foreign_bindings:
                    for target_symbol_id, target_terminal in foreign_bindings:
                        target_symbol = symbol_by_id[target_symbol_id]
                        pair = tuple(sorted(
                            (src_symbol_id, target_symbol_id)
                        ))

                        current = best_by_pair.get(pair)
                        if current is None or distance < current[0]:
                            best_by_pair[pair] = (
                                distance,
                                src_symbol,
                                target_symbol,
                                src_terminal,
                                target_terminal,
                                list(path),
                            )

                    # A symbol terminal is a tracing boundary: do not traverse
                    # through another equipment candidate.
                    continue

                for nb in tracing_graph.neighbors(node_id):
                    edge_data = tracing_graph.edges[node_id, nb]
                    step = float(edge_data.get("length_pt") or 0.0)
                    new_distance = distance + step

                    if new_distance > max_path_length:
                        continue
                    if new_distance + 1e-9 >= best_distance.get(
                        int(nb), float("inf")
                    ):
                        continue

                    best_distance[int(nb)] = new_distance
                    heapq.heappush(
                        heap,
                        (new_distance, int(nb), path + [int(nb)]),
                    )

    # Convert shortest symbol-pair paths to relation candidates.
    relations: List[TracedRelationCandidate] = []
    relation_seq = 0

    for pair in sorted(best_by_pair):
        (
            path_length,
            source,
            target,
            src_terminal,
            tgt_terminal,
            path_nodes,
        ) = best_by_pair[pair]

        # Canonicalize relation orientation only for deterministic storage.
        if source.symbol_id > target.symbol_id:
            source, target = target, source
            src_terminal, tgt_terminal = tgt_terminal, src_terminal
            path_nodes = list(reversed(path_nodes))

        path_edge_ids: List[int] = []
        branch_count = 0

        for node_id in path_nodes:
            node = node_by_id.get(node_id)
            if node and node.node_type in {
                "T_JUNCTION",
                "MULTI_JUNCTION",
            }:
                branch_count += 1

        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            if tracing_graph.has_edge(u, v):
                eid = tracing_graph.edges[u, v].get("edge_id")
                if eid is not None:
                    path_edge_ids.append(int(eid))

        relation_seq += 1
        relations.append(
            TracedRelationCandidate(
                relation_id=(
                    f"{doc_id}_P{page_no:03d}_TRACE_{relation_seq:04d}"
                ),
                source_symbol_id=source.symbol_id,
                target_symbol_id=target.symbol_id,
                relation_type="CONNECTS_TO_CANDIDATE",
                direction_status="UNRESOLVED",
                page=page_no,
                doc=doc_id,
                confidence=_confidence(
                    source,
                    target,
                    src_terminal,
                    tgt_terminal,
                    branch_count,
                    path_length,
                    max_path_length,
                ),
                source_terminal_id=src_terminal.terminal_id,
                target_terminal_id=tgt_terminal.terminal_id,
                path_length_pt=round(path_length, 3),
                path_node_ids=path_nodes,
                path_edge_ids=path_edge_ids,
                branch_node_count=branch_count,
                accepted_relation=False,
                evidence={
                    "method": "PLANAR_GRAPH_TERMINAL_TRACE",
                    "source_candidate_type": source.candidate_type,
                    "target_candidate_type": target.candidate_type,
                    "source_evidence_state": source.evidence_state,
                    "target_evidence_state": target.evidence_state,
                    "max_path_length_pt": round(max_path_length, 3),
                    "intermediate_foreign_terminal_count": 0,
                },
            )
        )

    # Limit pathological symbol fan-out without silently changing the actual
    # trace set: mark overflow rather than deleting all evidence globally.
    per_symbol = Counter()
    kept: List[TracedRelationCandidate] = []
    overflow: List[str] = []

    for rel in sorted(
        relations,
        key=lambda r: (-r.confidence, r.path_length_pt, r.relation_id),
    ):
        a = rel.source_symbol_id
        b = rel.target_symbol_id
        if (
            per_symbol[a] >= geom.trace_max_relations_per_symbol
            or per_symbol[b] >= geom.trace_max_relations_per_symbol
        ):
            overflow.append(rel.relation_id)
            continue

        kept.append(rel)
        per_symbol[a] += 1
        per_symbol[b] += 1

    kept.sort(key=lambda r: r.relation_id)

    type_pairs = Counter(
        " -> ".join(sorted((
            r.evidence["source_candidate_type"],
            r.evidence["target_candidate_type"],
        )))
        for r in kept
    )

    return {
        "status": "OK",
        "diagnostic_only": True,
        "accepted_relation_count": 0,
        "candidate_relation_count": len(kept),
        "relations": kept,
        "relation_type_pair_counts": dict(type_pairs),
        "max_path_length_pt": round(max_path_length, 3),
        "trace_eligible_symbol_count": graph_meta[
            "trace_eligible_symbol_count"
        ],
        "blocked_internal_edge_count": graph_meta[
            "blocked_internal_edge_count"
        ],
        "overflow_relation_count": len(overflow),
        "overflow_relation_ids": overflow,
        "tracing_graph_node_count": tracing_graph.number_of_nodes(),
        "tracing_graph_edge_count": tracing_graph.number_of_edges(),
    }
