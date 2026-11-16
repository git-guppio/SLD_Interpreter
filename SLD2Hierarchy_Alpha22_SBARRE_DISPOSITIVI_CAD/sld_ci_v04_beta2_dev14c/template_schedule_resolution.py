"""Cross-source template/schedule resolver for document families like Power Blocks.

This resolver is intentionally document-local.  It does not define POWER BLOCK,
SKID or XFR as global aliases for a Conversion Unit.  It infers a CU model only
when independent source domains converge within the current plant:

- positioned BLOCK SCHEDULE rows establish explicit block identities;
- SLD XFR tags establish explicit transformer identities;
- the two identifier sets align one-to-one;
- document semantics state POWER BLOCK/SKID context;
- inverter template evidence, when used, explicitly declares a typical inverter
  for the same skid population.

All synthesized asset instances retain INFERRED provenance.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


def _safe(v: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(v).upper()).strip("_") or "UNKNOWN"


def _sort_key(v: str):
    return (not str(v).isdigit(), int(v) if str(v).isdigit() else str(v))


def _xfr_instances(
    pages: List[Dict[str, Any]], allowed_page_roles: Optional[set[str]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in pages:
        if allowed_page_roles is not None and p.get("page_role") not in allowed_page_roles:
            continue
        for a in p.get("text_equipment_anchors", []) or []:
            if a.get("evidence_kind") != "XFR_TAG":
                continue
            n = (a.get("attributes", {}) or {}).get("xfr_instance_hint")
            if n is None:
                continue
            out[str(n)].append(a)
    return out


def _block_rows(layout_pages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    conflicts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in layout_pages:
        for row in p.get("block_schedule_rows", []) or []:
            key = str(row.get("block_instance_key"))
            if not key or key == "None":
                continue
            if row.get("status") == "CONFLICTING_SOURCE_ROWS":
                conflicts[key].append(row)
                continue
            if key in out and any(out[key].get(k) != row.get(k) for k in (
                "wiring_pattern", "combiner_box_count", "module_manufacturer", "detail_sheet"
            )):
                conflicts[key].extend([out[key], row])
                out.pop(key, None)
            elif key not in conflicts:
                out[key] = row
    for key in conflicts:
        out.pop(key, None)
    return out


def _semantic_summary(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    flags = {
        "has_power_block_family": False,
        "has_skid_family": False,
        "has_intermediate_step_up_transformer": False,
        "has_from_inverter": False,
        "has_combiner_box_family": False,
    }
    counts = set()
    skid_evidence = []
    for p in pages:
        s = p.get("document_semantics", {}) or {}
        for k in flags:
            flags[k] = flags[k] or bool(s.get(k))
        counts.update(int(x) for x in (s.get("typical_skid_counts", []) or []) if x is not None)
        skid_evidence.extend(s.get("typical_skid_evidence", []) or [])
    flags["typical_skid_counts"] = sorted(counts)
    flags["typical_skid_evidence"] = skid_evidence
    return flags


def resolve_template_schedule_model(
    sld_pages: List[Dict[str, Any]],
    layout_pages: List[Dict[str, Any]],
    *,
    plant_id: str,
) -> Dict[str, Any]:
    rows = _block_rows(layout_pages)
    xfr = _xfr_instances(sld_pages)
    layout_xfr = _xfr_instances(layout_pages, {"MV_NETWORK_LAYOUT"})
    sld_sem = _semantic_summary(sld_pages)
    layout_sem = _semantic_summary(layout_pages)

    block_ids = set(rows)
    xfr_ids = set(xfr)
    exact_identity_alignment = bool(block_ids) and block_ids == xfr_ids
    power_block_context = bool(rows) and (layout_sem.get("has_power_block_family") or any(
        p.get("page_role") == "CONTAINER_SCHEDULE" for p in layout_pages
    ))

    skid_counts = set(sld_sem.get("typical_skid_counts", []) or [])
    unique_skid_count = next(iter(skid_counts)) if len(skid_counts) == 1 else None
    inverter_template_supported = bool(
        exact_identity_alignment
        and sld_sem.get("has_skid_family")
        and unique_skid_count == len(block_ids)
    )
    transformer_role_supported = bool(
        exact_identity_alignment
        and sld_sem.get("has_intermediate_step_up_transformer")
        and sld_sem.get("has_from_inverter")
        and any(p.get("page_role") == "ELECTRICAL_SLD" for p in sld_pages)
    )
    cu_supported = bool(exact_identity_alignment and power_block_context)

    sld_doc = next((p.get("doc") for p in sld_pages if p.get("doc")), f"{plant_id}::SLD")

    container_entities: List[Dict[str, Any]] = []
    target_entities: List[Dict[str, Any]] = []
    layout_cu_representations: List[Dict[str, Any]] = []

    if cu_supported:
        for key in sorted(block_ids, key=_sort_key):
            row = rows[key]
            container_entities.append({
                "entity_id": f"{sld_doc}::CU::{_safe(key)}",
                "entity_type": "CONVERSION_UNIT",
                "doc": sld_doc,
                "instance_key": key,
                "canonical_label": f"POWER BLOCK {key}",
                "source_status": "INFERRED",
                "source_labels": [f"BLOCK {key}", f"XFR_{key}"],
                "representations": [{
                    "page": row.get("page"),
                    "text": f"BLOCK {key}",
                    "anchor_id": None,
                    "representation_role": "SCHEDULE_INSTANCE",
                    "source_status": "DETECTED",
                    "pattern_id": None,
                }],
                "inference_basis": "DOCUMENT_LOCAL_BLOCK_XFR_IDENTITY_ALIGNMENT",
            })

        # After the document-local equivalence is established, XFR labels in the
        # layout can act as representations of their parent Power Block/CU.  They
        # are not globally redefined as CUs.
        for key in sorted(block_ids, key=_sort_key):
            for a in layout_xfr.get(key, []):
                layout_cu_representations.append({
                    "cu_instance_key": key,
                    "page": a.get("page"),
                    "doc": a.get("doc"),
                    "anchor_id": a.get("anchor_id"),
                    "text": a.get("text"),
                    "bbox": a.get("bbox"),
                    "graph_binding": None,
                    "source_status": "INFERRED",
                    "representation_basis": "DOCUMENT_LOCAL_XFR_REPRESENTS_POWER_BLOCK_AFTER_ID_ALIGNMENT",
                })

    if transformer_role_supported:
        for key in sorted(block_ids, key=_sort_key):
            anchors = xfr.get(key, [])
            target_entities.append({
                "equipment_id": f"{sld_doc}::MV_LV_TRANSFORMER::XFR_{_safe(key)}",
                "equipment_type": "MV_LV_TRANSFORMER",
                "doc": sld_doc,
                "tag": f"XFR_{key}",
                "source_symbol_ids": [],
                "occurrences": [
                    {"page": a.get("page"), "bbox": a.get("bbox"), "anchor_id": a.get("anchor_id")}
                    for a in anchors
                ],
                "anchor_ids": [a.get("anchor_id") for a in anchors if a.get("anchor_id")],
                "acceptance_reason": "XFR_INSTANCE_PLUS_DOCUMENT_LOCAL_STEP_UP_TRANSFORMER_SEMANTICS",
                "confidence": 0.96,
                "source_status": "INFERRED",
                "evidence_mode": "CROSS_SOURCE_SEMANTIC_CLASSIFICATION",
                "cu_instance_hint": key,
                "membership_basis_hint": "DOCUMENT_LOCAL_BLOCK_XFR_IDENTITY_ALIGNMENT",
            })

    if inverter_template_supported and cu_supported:
        for key in sorted(block_ids, key=_sort_key):
            inv_id = f"{sld_doc}::CENTRAL_INVERTER::BLOCK_{_safe(key)}"
            template_ev = (sld_sem.get("typical_skid_evidence") or [{}])[0]
            target_entities.append({
                "equipment_id": inv_id,
                "equipment_type": "CENTRAL_INVERTER",
                "doc": sld_doc,
                "tag": None,
                "source_symbol_ids": [],
                "occurrences": [{
                    "page": template_ev.get("page"),
                    "bbox": template_ev.get("bbox"),
                    "anchor_id": None,
                }],
                "anchor_ids": [],
                "acceptance_reason": "DOCUMENT_TEMPLATE_ONE_INVERTER_PER_EXPLICIT_SKID_INSTANCE",
                "confidence": 0.93,
                "source_status": "INFERRED",
                "evidence_mode": "TEMPLATE_INSTANCE_EXPANSION",
                "cu_instance_hint": key,
                "inverter_instance_hint": "1",
                "membership_basis_hint": "TYPICAL_INVERTER_FOR_EXPLICIT_SKID_POPULATION",
            })

            count = int(rows[key].get("combiner_box_count") or 0)
            for ordinal in range(1, count + 1):
                target_entities.append({
                    "equipment_id": f"{sld_doc}::STRING_BOX::BLOCK_{_safe(key)}::ORD_{ordinal:02d}",
                    "equipment_type": "STRING_BOX",
                    "doc": sld_doc,
                    "tag": None,
                    "source_symbol_ids": [],
                    "occurrences": [{
                        "page": rows[key].get("page"),
                        "bbox": rows[key].get("bbox"),
                        "anchor_id": None,
                    }],
                    "anchor_ids": [],
                    "acceptance_reason": "POSITIONED_BLOCK_SCHEDULE_COMBINER_CARDINALITY",
                    "confidence": 0.92,
                    "source_status": "INFERRED",
                    "evidence_mode": "SCHEDULE_CARDINALITY_EXPANSION",
                    "cu_instance_hint": key,
                    "inverter_instance_hint": "1",
                    "string_box_instance_hint": str(ordinal),
                    "membership_basis_hint": "BLOCK_SCHEDULE_COMBINER_CARDINALITY",
                })

    inferred_counts = defaultdict(int)
    for e in target_entities:
        inferred_counts[e.get("equipment_type")] += 1

    diagnostics = []
    if rows and xfr_ids and not exact_identity_alignment:
        diagnostics.append({
            "status": "BLOCK_XFR_IDENTITY_SETS_DO_NOT_ALIGN",
            "block_only": sorted(block_ids - xfr_ids, key=_sort_key),
            "xfr_only": sorted(xfr_ids - block_ids, key=_sort_key),
            "policy": "NO_CU_ALIAS_INFERENCE_WHEN_IDENTITY_ALIGNMENT_FAILS",
        })

    return {
        "status": "RESOLVED" if cu_supported else "NO_DOCUMENT_LOCAL_CONTAINER_MODEL",
        "plant_id": plant_id,
        "block_schedule_rows": [rows[k] for k in sorted(rows, key=_sort_key)],
        "block_schedule_row_count": len(rows),
        "block_schedule_combiner_total": sum(int(r.get("combiner_box_count") or 0) for r in rows.values()),
        "sld_xfr_instance_count": len(xfr_ids),
        "identity_alignment": {
            "exact_block_xfr_instance_set_match": exact_identity_alignment,
            "block_instance_count": len(block_ids),
            "xfr_instance_count": len(xfr_ids),
        },
        "semantic_support": {
            "power_block_context": power_block_context,
            "typical_skid_count": unique_skid_count,
            "inverter_template_supported": inverter_template_supported,
            "transformer_role_supported": transformer_role_supported,
        },
        "container_entities": container_entities,
        "target_entities": target_entities,
        "layout_cu_representations": layout_cu_representations,
        "inferred_target_counts": dict(inferred_counts),
        "diagnostics": diagnostics,
        "policy": "DOCUMENT_LOCAL_TEMPLATE_AND_SCHEDULE_CONVERGENCE_ONLY;_NO_GLOBAL_POWER_BLOCK_OR_XFR_ALIAS",
    }
