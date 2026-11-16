"""Reconcile SLD and optional layout at plant level.

Only CU identity is reconciled in dev6.  Equipment remains sourced from the SLD
hierarchy.  Layout information adds representations and optional MV-line
membership; it never creates duplicate equipment instances.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List


def _safe(v: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(v).upper()).strip("_") or "UNKNOWN"


def reconcile_sources(
    plant_id: str,
    sld_container_resolution: Dict[str, Any],
    layout_resolution: Dict[str, Any],
) -> Dict[str, Any]:
    sld_cus = list((sld_container_resolution or {}).get("entities", []) or [])
    layout_reps = list((layout_resolution or {}).get("conversion_unit_representations", []) or [])
    layout_membership = list((layout_resolution or {}).get("cu_mv_membership", []) or [])

    by_key: Dict[str, Dict[str, Any]] = {}
    for c in sld_cus:
        key = str(c.get("instance_key"))
        row = by_key.setdefault(key, {
            "canonical_cu_id": f"{plant_id}::CU::{_safe(key)}",
            "instance_key": key,
            "sld_entity_ids": [],
            "sld_representations": [],
            "layout_representations": [],
            "mv_line_instance_keys": [],
            "source_status": c.get("source_status", "DETECTED"),
        })
        row["sld_entity_ids"].append(c.get("entity_id"))
        row["sld_representations"].extend(c.get("representations", []) or [])

    for r in layout_reps:
        key = str(r.get("cu_instance_key"))
        row = by_key.setdefault(key, {
            "canonical_cu_id": f"{plant_id}::CU::{_safe(key)}",
            "instance_key": key,
            "sld_entity_ids": [],
            "sld_representations": [],
            "layout_representations": [],
            "mv_line_instance_keys": [],
            "source_status": "DETECTED",
        })
        row["layout_representations"].append(r)

    for m in layout_membership:
        key = str(m.get("cu_instance_key"))
        if key not in by_key:
            continue
        lk = str(m.get("mv_line_instance_key"))
        if lk not in by_key[key]["mv_line_instance_keys"]:
            by_key[key]["mv_line_instance_keys"].append(lk)

    rows = [by_key[k] for k in sorted(by_key, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))]
    for r in rows:
        in_sld = bool(r["sld_entity_ids"])
        in_layout = bool(r["layout_representations"])
        r["source_coverage"] = {
            "sld": in_sld,
            "layout": in_layout,
        }
        if in_sld and in_layout:
            r["reconciliation_status"] = "MATCHED_ACROSS_SOURCES"
        elif in_sld:
            r["reconciliation_status"] = "SLD_ONLY"
        else:
            r["reconciliation_status"] = "LAYOUT_ONLY"

    return {
        "plant_id": plant_id,
        "conversion_units": rows,
        "mv_lines": list((layout_resolution or {}).get("mv_lines", []) or []),
        "cu_mv_membership": layout_membership,
        "unresolved_layout_membership": list((layout_resolution or {}).get("unresolved_membership", []) or []),
        "unresolved_mv_line_labels": list((layout_resolution or {}).get("unresolved_line_labels", []) or []),
        "summary": {
            "canonical_conversion_unit_count": len(rows),
            "matched_across_sources": sum(r["reconciliation_status"] == "MATCHED_ACROSS_SOURCES" for r in rows),
            "sld_only": sum(r["reconciliation_status"] == "SLD_ONLY" for r in rows),
            "layout_only": sum(r["reconciliation_status"] == "LAYOUT_ONLY" for r in rows),
            "mv_line_count": len((layout_resolution or {}).get("mv_lines", []) or []),
            "resolved_cu_mv_membership_count": len(layout_membership),
            "unresolved_mv_line_label_count": len((layout_resolution or {}).get("unresolved_line_labels", []) or []),
            "resolved_mv_line_label_count": int(((layout_resolution or {}).get("summary", {}) or {}).get("resolved_mv_line_label_count") or 0),
            "operator_or_learned_mv_line_label_count": int(((layout_resolution or {}).get("summary", {}) or {}).get("operator_or_learned_mv_line_label_count") or 0),
            "explicit_schedule_membership_count": int(((layout_resolution or {}).get("summary", {}) or {}).get("explicit_schedule_membership_count") or 0),
            "graph_verified_cu_mv_membership_count": int(((layout_resolution or {}).get("summary", {}) or {}).get("graph_verified_cu_mv_membership_count") or 0),
            "membership_hard_conflict_count": int(((layout_resolution or {}).get("summary", {}) or {}).get("membership_hard_conflict_count") or 0),
            "weak_geometry_disagreement_count": int(((layout_resolution or {}).get("summary", {}) or {}).get("weak_geometry_disagreement_count") or 0),
        },
        "policy": "CANONICAL_CU_IDENTITY_BY_EXPLICIT_INSTANCE_KEY;_LAYOUT_ADDS_TOPOLOGY_BUT_NOT_EQUIPMENT_COUNTS",
    }
