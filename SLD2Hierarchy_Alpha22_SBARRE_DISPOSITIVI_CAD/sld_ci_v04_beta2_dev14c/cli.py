from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf as fitz

from .config import RunConfig
from .decision_pipeline import interpret
from .knowledge_store import KnowledgeStore
from .operator_interaction import validate_feedback_batch
from .operator_learning import patterns_from_feedback
from .schedule_evidence import extract_schedule_evidence, extract_block_schedule_rows, extract_mv_circuit_schedule_rows
from .document_semantics import extract_document_semantics
from .template_schedule_resolution import resolve_template_schedule_model
from .ingestion import (
    classify_page_lightweight,
    extract_orthogonal_vector_inventory,
    native_text_items,
    ocr_text_items_tiled,
)
from .line_tracing import trace_terminal_to_terminal
from .scale_coherence import apply_ci_scale_coherence, find_text_guided_ci_scale_references
from .symbol_detection import detect_vector_symbol_candidates, fuse_text_and_vector_candidates
from .text_detection import detect_text_equipment_anchors
from .vector_graph import build_electrical_planar_graph
from .target_summary import summarize_target_hierarchy
from .layout_evidence import detect_mv_line_anchors
from .layout_resolution import resolve_layout, build_layout_resolution_requests
from .layout_feeder_recovery import recover_layout_feeder_candidates
from .source_reconciliation import reconcile_sources
from .feeder_verification import resolve_feeder_verification, apply_feeder_membership_to_layout_resolution
from .source_resolution import (
    SOURCE_LAYOUT,
    SOURCE_SLD,
    resolve_page_role,
    source_doc_id,
    validate_source_pair,
)


def analyze_page(
    page: fitz.Page,
    page_no: int,
    doc_id: str,
    config: RunConfig,
    *,
    source_role: str = SOURCE_SLD,
    plant_id: Optional[str] = None,
    source_file: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()

    native_items, native_meta = native_text_items(page, page_no, doc_id)
    text_items = list(native_items)
    ocr_meta: Dict[str, Any] = {}

    run_ocr = (
        config.ocr_mode == "always"
        or (config.ocr_mode == "auto" and not native_meta.get("native_text_usable"))
    )
    if run_ocr:
        ocr_items, ocr_meta = ocr_text_items_tiled(
            page, page_no, doc_id, dpi=config.dpi, lang=config.lang
        )
        text_items.extend(ocr_items)

    page_type, page_type_reasons = classify_page_lightweight(text_items)
    block_schedule_rows = extract_block_schedule_rows(text_items)
    mv_circuit_schedule_rows = extract_mv_circuit_schedule_rows(text_items)
    document_semantics = extract_document_semantics(text_items)

    vec = extract_orthogonal_vector_inventory(page, config.geometry)
    accepted = vec["accepted_segments"]
    graph = build_electrical_planar_graph(
        accepted,
        page_w=vec["page_width_pt"],
        page_h=vec["page_height_pt"],
        geom=config.geometry,
    )

    text_anchors = detect_text_equipment_anchors(text_items)
    # Dev10 detects explicit MV identifiers on both sources. Layout uses
    # them for plant-line inventory; SLD uses them only as trace evidence.
    layout_mv_line_anchors = detect_mv_line_anchors(text_items, page_no, doc_id)
    layout_feeder_candidates = (
        recover_layout_feeder_candidates(page, page_no, doc_id, accepted)
        if str(source_role).upper() == SOURCE_LAYOUT else []
    )

    vector_candidates = detect_vector_symbol_candidates(
        page, page_no, doc_id, graph_nodes=graph["nodes"], geom=config.geometry
    )
    symbol_candidates = fuse_text_and_vector_candidates(
        vector_candidates,
        text_anchors,
        page_w=vec["page_width_pt"],
        page_h=vec["page_height_pt"],
        geom=config.geometry,
    )

    scale_refs = find_text_guided_ci_scale_references(page, text_anchors, config.geometry)
    scale_eval = apply_ci_scale_coherence(
        symbol_candidates, scale_refs,
        page_no=page_no, doc_id=doc_id, geom=config.geometry,
    )
    tracing = trace_terminal_to_terminal(
        graph_nodes=graph["nodes"],
        graph_edges=graph["edges"],
        symbols=symbol_candidates,
        page_no=page_no,
        doc_id=doc_id,
        page_w=vec["page_width_pt"],
        page_h=vec["page_height_pt"],
        geom=config.geometry,
    )

    candidate_type_counts = Counter(s.candidate_type for s in symbol_candidates)
    evidence_state_counts = Counter(s.evidence_state for s in symbol_candidates)
    terminal_count = sum(len(s.terminals) for s in symbol_candidates)
    candidates_with_terminals = sum(1 for s in symbol_candidates if s.terminals)

    result: Dict[str, Any] = {
        "page": page_no,
        "doc": doc_id,
        "plant_id": plant_id,
        "source_role": str(source_role).upper(),
        "source_file": source_file,
        "page_type": page_type,
        "page_width_pt": vec["page_width_pt"],
        "page_height_pt": vec["page_height_pt"],
        "rotation_degrees": int(page.rotation),
        "planar_graph": {
            "source_segment_count": graph["source_segment_count"],
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "crossing_count": len(graph["crossings"]),
            "connected_component_count": graph["connected_component_count"],
            "node_type_counts": graph["node_type_counts"],
            "nodes": [asdict(n) for n in graph["nodes"]],
            "edges": [asdict(e) for e in graph["edges"]],
            "crossings": [asdict(c) for c in graph["crossings"]],
            "component_summaries": graph["component_summaries"],
            "snap_tolerance_pt": graph["snap_tolerance_pt"],
            "touch_tolerance_pt": graph["touch_tolerance_pt"],
        },
        "text_equipment_anchors": [asdict(a) for a in text_anchors],
        "layout_mv_line_anchors": layout_mv_line_anchors,
        "layout_feeder_candidates": layout_feeder_candidates,
        "schedule_evidence": extract_schedule_evidence(text_items),
        "block_schedule_rows": block_schedule_rows,
        "mv_circuit_schedule_rows": mv_circuit_schedule_rows,
        "document_semantics": document_semantics,
        "vector_symbol_candidates": [asdict(s) for s in vector_candidates],
        "symbol_candidates": [asdict(s) for s in symbol_candidates],
        "symbol_scale_coherence": scale_eval,
        "symbol_summary": {
            "text_anchor_count": len(text_anchors),
            "vector_candidate_count": len(vector_candidates),
            "candidate_count": len(symbol_candidates),
            "candidate_type_counts": dict(candidate_type_counts),
            "evidence_state_counts": dict(evidence_state_counts),
            "terminal_binding_count": terminal_count,
            "candidates_with_terminals": candidates_with_terminals,
            "ci_scale_reference_count": scale_eval["reference_count"],
            "ci_scale_outlier_count": scale_eval["scale_outlier_count"],
            "ci_scale_consistent_count": scale_eval["scale_consistent_count"],
            "text_guided_ci_candidates_added": scale_eval["text_guided_ci_candidates_added"],
            "mv_line_anchor_count": len(layout_mv_line_anchors),
            "layout_feeder_candidate_count": len(layout_feeder_candidates),
            "block_schedule_row_count": len(block_schedule_rows),
            "mv_circuit_schedule_row_count": len(mv_circuit_schedule_rows),
        },
        "terminal_tracing": {
            **{k: v for k, v in tracing.items() if k != "relations"},
            "relations": [asdict(r) for r in tracing["relations"]],
        },
        "meta": {
            "page_type_reasons": page_type_reasons,
            "native": native_meta,
            "ocr": ocr_meta,
            "vector": {
                "drawing_path_count": vec["drawing_path_count"],
                "line_items_scanned": vec["line_items_scanned"],
                "near_black_line_items_scanned": vec["near_black_line_items_scanned"],
                "scan_truncated": vec["scan_truncated"],
                "profile_by_stroke_color": vec["profile_by_stroke_color"],
            },
            "processing_seconds": round(time.perf_counter() - t0, 4),
        },
    }
    result["page_role_resolution"] = resolve_page_role(result, source_role)
    result["page_role"] = result["page_role_resolution"]["page_role"]
    return result


def _source_counts_empty() -> Dict[str, Any]:
    return {
        "totals": Counter(),
        "candidate_types": Counter(),
        "evidence_states": Counter(),
    }


def _accumulate_page_counts(acc: Dict[str, Any], p: Dict[str, Any]) -> None:
    pg = p["planar_graph"]
    ss = p["symbol_summary"]
    tr = p["terminal_tracing"]
    totals: Counter = acc["totals"]
    totals["nodes"] += pg["node_count"]
    totals["edges"] += pg["edge_count"]
    totals["crossings"] += pg["crossing_count"]
    totals["components"] += pg["connected_component_count"]
    totals["text_anchors"] += ss["text_anchor_count"]
    totals["vector_candidates"] += ss["vector_candidate_count"]
    totals["symbol_candidates"] += ss["candidate_count"]
    totals["terminal_bindings"] += ss["terminal_binding_count"]
    totals["candidates_with_terminals"] += ss["candidates_with_terminals"]
    totals["ci_scale_references"] += ss["ci_scale_reference_count"]
    totals["ci_scale_outliers"] += ss["ci_scale_outlier_count"]
    totals["text_guided_ci_candidates"] += ss["text_guided_ci_candidates_added"]
    totals["trace_eligible_symbols"] += tr["trace_eligible_symbol_count"]
    totals["traced_candidate_relations"] += tr["candidate_relation_count"]
    totals["accepted_relations"] += tr["accepted_relation_count"]
    totals["mv_line_anchors"] += ss.get("mv_line_anchor_count", 0)
    totals["layout_feeder_candidates"] += ss.get("layout_feeder_candidate_count", 0)
    totals["block_schedule_rows"] += ss.get("block_schedule_row_count", 0)
    totals["mv_circuit_schedule_rows"] += ss.get("mv_circuit_schedule_row_count", 0)
    acc["candidate_types"].update(ss["candidate_type_counts"])
    acc["evidence_states"].update(ss["evidence_state_counts"])


def _analyze_source(
    pdf_path: str,
    *,
    source_role: str,
    plant_id: str,
    config: RunConfig,
) -> Dict[str, Any]:
    pdf = fitz.open(pdf_path)
    doc_id = source_doc_id(plant_id, source_role)
    page_limit = pdf.page_count if config.max_pages is None else min(pdf.page_count, config.max_pages)
    pages: List[Dict[str, Any]] = []
    acc = _source_counts_empty()

    for i in range(page_limit):
        page_no = i + 1
        print(f"[{Path(pdf_path).name} | {source_role}] page {page_no}/{pdf.page_count} ...")
        try:
            p = analyze_page(
                pdf[i], page_no, doc_id, config,
                source_role=source_role,
                plant_id=plant_id,
                source_file=Path(pdf_path).name,
            )
            pages.append(p)
            _accumulate_page_counts(acc, p)
            pg = p["planar_graph"]
            ss = p["symbol_summary"]
            tr = p["terminal_tracing"]
            print(
                "  -> "
                f"role={p['page_role']} | type={p['page_type']} | "
                f"graph={pg['node_count']}N/{pg['edge_count']}E | "
                f"text_anchors={ss['text_anchor_count']} | "
                f"mv_line_anchors={ss.get('mv_line_anchor_count', 0)} | "
                f"feeder_candidates={ss.get('layout_feeder_candidate_count', 0)} | "
                f"trace_eligible={tr['trace_eligible_symbol_count']} | "
                f"accepted=deferred_to_document_decision_stage"
            )
        except Exception as exc:
            pages.append({
                "page": page_no,
                "doc": doc_id,
                "plant_id": plant_id,
                "source_role": source_role,
                "source_file": Path(pdf_path).name,
                "page_type": "ERROR",
                "page_role": "ERROR",
                "error": str(exc),
            })
            print(f"  -> ERROR: {exc}")

    return {
        "document": {
            "doc_id": doc_id,
            "file_name": Path(pdf_path).name,
            "source_role": source_role,
            "page_count": pdf.page_count,
            "processed_pages": page_limit,
            "analysis_complete": page_limit == pdf.page_count and all(p.get("page_type") != "ERROR" for p in pages),
        },
        "pages": pages,
        "counts": {
            **dict(acc["totals"]),
            "candidate_types": dict(acc["candidate_types"]),
            "evidence_states": dict(acc["evidence_states"]),
        },
    }


def _load_operator_context(knowledge_path: Optional[str], operator_feedback_path: Optional[str]):
    operator_feedback = []
    learned_patterns = []
    store = None
    if knowledge_path:
        store = KnowledgeStore(knowledge_path)
        learned_patterns = store.patterns()
    if operator_feedback_path:
        raw_feedback = json.loads(Path(operator_feedback_path).read_text(encoding="utf-8"))
        if isinstance(raw_feedback, dict):
            raw_feedback = raw_feedback.get("operator_feedback", raw_feedback.get("records", []))
        operator_feedback = validate_feedback_batch(raw_feedback or [])
        if store is not None:
            for fb in operator_feedback:
                store.add_feedback(fb)
            for pat in patterns_from_feedback(operator_feedback):
                store.add_pattern(pat)
            store.save()
            learned_patterns = store.patterns()
    return learned_patterns, operator_feedback


def run_case(
    sld_path: str,
    out_path: str,
    config: RunConfig,
    *,
    layout_path: Optional[str] = None,
    plant_id: Optional[str] = None,
    knowledge_path: Optional[str] = None,
    operator_feedback_path: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    source_pair = validate_source_pair(sld_path, layout_path, plant_id=plant_id)
    plant_id = source_pair["plant_id"]

    sld = _analyze_source(sld_path, source_role=SOURCE_SLD, plant_id=plant_id, config=config)
    layout = (
        _analyze_source(layout_path, source_role=SOURCE_LAYOUT, plant_id=plant_id, config=config)
        if layout_path else None
    )

    learned_patterns, operator_feedback = _load_operator_context(knowledge_path, operator_feedback_path)

    # Dev9 cross-source resolver: auxiliary layout/schedule evidence may establish
    # document-local CU identities and template cardinalities, but only through
    # explicit convergence with SLD instance evidence.  No global alias is added.
    template_schedule_resolution = resolve_template_schedule_model(
        sld["pages"], layout["pages"] if layout else [], plant_id=plant_id
    )

    interpretation = interpret(
        sld["pages"], config.geometry,
        learned_patterns=learned_patterns,
        operator_feedback=operator_feedback,
        supplemental_container_entities=template_schedule_resolution.get("container_entities", []),
        supplemental_target_entities=template_schedule_resolution.get("target_entities", []),
    )
    layout_resolution = resolve_layout(
        layout["pages"] if layout else [],
        operator_feedback=operator_feedback,
        learned_patterns=learned_patterns,
        plant_id=plant_id,
        supplemental_cu_representations=template_schedule_resolution.get("layout_cu_representations", []),
    )

    # Dev10 keeps source-explicit CU→feeder membership separate from electrical
    # graph verification.  A circuit schedule may resolve membership while the
    # trace remains explicitly NOT_FULLY_GRAPH_VERIFIED.
    feeder_verification = resolve_feeder_verification(
        sld["pages"],
        layout["pages"] if layout else [],
        template_schedule_resolution=template_schedule_resolution,
        legacy_layout_resolution=layout_resolution,
        plant_id=plant_id,
        operator_feedback=operator_feedback,
        learned_patterns=learned_patterns,
    )
    layout_resolution = apply_feeder_membership_to_layout_resolution(
        layout_resolution, feeder_verification
    )
    layout_resolution_requests = build_layout_resolution_requests(
        layout_resolution, plant_id=plant_id, operator_feedback=operator_feedback
    )
    feeder_verification_requests = list(feeder_verification.get("resolution_requests", []) or [])
    source_reconciliation = reconcile_sources(
        plant_id,
        interpretation.get("container_resolution", {}),
        layout_resolution,
    )

    analysis_counts = {
        "sld": {
            **sld["counts"],
            "accepted_equipment": len(interpretation["accepted_equipment"]),
            "accepted_relations": len(interpretation["accepted_relations"]),
        },
        "layout": layout["counts"] if layout else None,
        "note": "SOURCE-SEPARATED RAW/INTERMEDIATE COUNTS; LAYOUT IS NOT INCLUDED IN TARGET EQUIPMENT COUNTS",
    }

    target_counts = summarize_target_hierarchy(interpretation["target_hierarchy"])
    sld_cu_count = int(target_counts.get("conversion_units") or 0)
    canonical_cu_count = int(source_reconciliation.get("summary", {}).get("canonical_conversion_unit_count") or sld_cu_count)
    target_counts["conversion_units_sld_hierarchy"] = sld_cu_count
    target_counts["conversion_units"] = canonical_cu_count
    target_counts["layout_only_conversion_units"] = int(source_reconciliation.get("summary", {}).get("layout_only") or 0)
    target_counts["cu_count_basis"] = "CANONICAL_EXPLICIT_CU_IDENTITIES_ACROSS_SLD_AND_OPTIONAL_LAYOUT"

    result = {
        "version": "0.4.0-beta2-dev14",
        "scope": "PV_CENTRAL_INVERTER_ONLY",
        "milestone": "BREAKPOINT_CLASSIFICATION_AND_DEVICE_GUARDRAIL",
        "plant": {
            "plant_id": plant_id,
            "source_name_validation": source_pair,
        },
        "inference_policy": {
            "ground_truth_used": False,
            "hierarchy_built": True,
            "layout_optional": True,
            "layout_used_as_equipment_inventory": False,
            "page_one_assumed_overview": False,
            "operator_mv_line_label_mapping_supported": True,
            "learned_mv_line_mapping_scope": "PLANT_ONLY",
            "document_local_template_schedule_resolution": True,
            "explicit_mv_circuit_schedule_membership": True,
            "feeder_graph_verification_separate_from_membership": True,
            "operator_assists_trace_breakpoints_not_bulk_membership": True,
            "operator_xfr_terminal_pattern_supported": True,
            "operator_conductive_gap_bridge_pattern_supported": True,
            "operator_breakpoint_classification_supported": True,
            "interposed_device_never_auto_bridged": True,
            "operator_graph_patterns_scope": "PLANT_ONLY",
            "global_power_block_xfr_alias": False,
            "accepted_equipment_created": bool(interpretation["accepted_equipment"]),
            "candidate_connectivity_created": True,
            "accepted_relations_created": bool(interpretation["accepted_relations"]),
        },
        "sources": {
            "sld": sld["document"],
            "layout": layout["document"] if layout else {"present": False, "source_role": SOURCE_LAYOUT},
        },
        # Backward-compatible primary document/page fields refer only to SLD.
        "document": sld["document"],
        "pages": sld["pages"],
        "layout_pages": layout["pages"] if layout else [],
        "interpretation": interpretation,
        "layout_resolution": layout_resolution,
        "template_schedule_resolution": template_schedule_resolution,
        "feeder_verification": feeder_verification,
        "layout_resolution_requests": layout_resolution_requests,
        "feeder_verification_requests": feeder_verification_requests,
        "resolution_requests": list(interpretation.get("resolution_requests", []) or []) + layout_resolution_requests + feeder_verification_requests,
        "source_reconciliation": source_reconciliation,
        "analysis_counts": analysis_counts,
        "counts": analysis_counts["sld"],
        "target_counts": target_counts,
        "processing_seconds": round(time.perf_counter() - t0, 4),
    }

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def run(pdf_path: str, out_path: str, config: RunConfig, knowledge_path: str | None = None, operator_feedback_path: str | None = None) -> Dict[str, Any]:
    """Backward-compatible single-source entry point: legacy --pdf is treated as SLD."""
    return run_case(
        pdf_path, out_path, config,
        layout_path=None,
        knowledge_path=knowledge_path,
        operator_feedback_path=operator_feedback_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sld-ci-v04-beta2-dev14",
        description=(
            "Electrical SLD Interpreter v0.4-beta2-dev14 — simplified operator workflow"
        ),
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--sld", help="Primary SLD PDF (recommended, e.g. PV8_SLD.pdf)")
    src.add_argument("--pdf", help="Legacy single-PDF mode; treated as the primary SLD")
    parser.add_argument("--layout", default=None, help="Optional plant layout PDF (e.g. PV8_LAYOUT.pdf)")
    parser.add_argument("--plant-id", default=None, help="Optional explicit plant key when filenames do not share the same PVx stem")
    parser.add_argument("--out", required=True)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--lang", default="eng+spa")
    parser.add_argument("--ocr-mode", choices=["never", "auto", "always"], default="auto")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--knowledge-store", default=None)
    parser.add_argument("--operator-feedback", default=None)
    args = parser.parse_args()

    if args.pdf and args.layout:
        parser.error("--layout is supported with --sld. Use --sld for the primary source in multi-source mode.")

    cfg = RunConfig(dpi=args.dpi, lang=args.lang, ocr_mode=args.ocr_mode, max_pages=args.max_pages)
    sld_path = args.sld or args.pdf
    result = run_case(
        sld_path,
        args.out,
        cfg,
        layout_path=args.layout,
        plant_id=args.plant_id,
        knowledge_path=args.knowledge_store,
        operator_feedback_path=args.operator_feedback,
    )

    print("\nANALYSIS COUNTS — SLD (raw/intermediate):")
    print(json.dumps(result["analysis_counts"]["sld"], indent=2))
    if result["analysis_counts"]["layout"] is not None:
        print("\nANALYSIS COUNTS — LAYOUT (auxiliary only):")
        print(json.dumps(result["analysis_counts"]["layout"], indent=2))
    print("\nDOCUMENT-LOCAL TEMPLATE/SCHEDULE RESOLUTION:")
    ts = result.get("template_schedule_resolution", {}) or {}
    print(json.dumps({
        "status": ts.get("status"),
        "block_schedule_row_count": ts.get("block_schedule_row_count"),
        "block_schedule_combiner_total": ts.get("block_schedule_combiner_total"),
        "sld_xfr_instance_count": ts.get("sld_xfr_instance_count"),
        "identity_alignment": ts.get("identity_alignment"),
        "semantic_support": ts.get("semantic_support"),
        "inferred_target_counts": ts.get("inferred_target_counts"),
    }, indent=2))
    print("\nFEEDER MEMBERSHIP / TOPOLOGY VERIFICATION:")
    fv = result.get("feeder_verification", {}) or {}
    print(json.dumps(fv.get("summary", {}), indent=2))
    if fv.get("operator_graph_calibration"):
        print("\nOPERATOR GRAPH CALIBRATION:")
        print(json.dumps(fv.get("operator_graph_calibration", {}), indent=2))
    print("\nTARGET COUNTS (resolved SLD hierarchy only):")
    print(json.dumps(result["target_counts"], indent=2))
    print("\nPLANT SOURCE RECONCILIATION:")
    print(json.dumps(result["source_reconciliation"]["summary"], indent=2))
    if result.get("layout_resolution_requests"):
        print("\nOPEN LAYOUT RESOLUTION REQUESTS:")
        for req in result["layout_resolution_requests"]:
            print(json.dumps({
                "request_id": req.get("request_id"),
                "target": req.get("target"),
                "reason": req.get("reason"),
                "mapping_keys": (req.get("context") or {}).get("mapping_keys", []),
            }, indent=2))
    if result.get("feeder_verification_requests"):
        print("\nOPEN FEEDER VERIFICATION REQUESTS:")
        for req in result["feeder_verification_requests"]:
            print(json.dumps({
                "request_id": req.get("request_id"),
                "target": req.get("target"),
                "reason": req.get("reason"),
                "interaction_mode": req.get("interaction_mode"),
                "feeder_count": (req.get("context") or {}).get("feeder_count"),
            }, indent=2))
    print(f"Output: {args.out}")
    return 0 if result["interpretation"]["validation"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
