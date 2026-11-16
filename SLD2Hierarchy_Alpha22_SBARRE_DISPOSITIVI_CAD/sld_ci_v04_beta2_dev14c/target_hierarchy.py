"""Build the minimum target hierarchy from resolved containers/equipment.

Counts are derived from resolved membership, never from global totals.
Only explicit semantic instance hints or explicit operator parent context are
used in dev2. Missing membership stays unresolved.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


def _anchor_index(pages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {a.get("anchor_id"): a for p in pages for a in p.get("text_equipment_anchors", []) if a.get("anchor_id")}


def _unique_hint(anchors, key: str) -> Optional[str]:
    vals = {str((a.get("attributes", {}) or {}).get(key)) for a in anchors if (a.get("attributes", {}) or {}).get(key) is not None}
    return next(iter(vals)) if len(vals) == 1 else None


def build_target_hierarchy(
    pages: List[Dict[str, Any]],
    container_resolution: Dict[str, Any],
    equipment: List[Dict[str, Any]],
) -> Dict[str, Any]:
    aidx = _anchor_index(pages)
    cus = list(container_resolution.get("entities", []))
    cu_by_key = {(c.get("doc"), str(c.get("instance_key"))): c for c in cus}

    inv_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    nodes: Dict[str, Dict[str, Any]] = {}
    unresolved_membership: List[Dict[str, Any]] = []

    for c in cus:
        nodes[c["entity_id"]] = {
            "entity_id": c["entity_id"],
            "entity_type": "CONVERSION_UNIT",
            "source_status": c.get("source_status"),
            "parent_id": None,
            "children": [],
            "instance_key": c.get("instance_key"),
            "label": c.get("canonical_label"),
        }

    # First pass: resolve CU membership of directly tagged target equipment.
    for e in equipment:
        et = e.get("equipment_type")
        if et not in {"IOCB", "MV_LV_TRANSFORMER", "CENTRAL_INVERTER", "LV_LV_TRANSFORMER", "STRING_BOX"}:
            continue
        anchors = [aidx[x] for x in e.get("anchor_ids", []) if x in aidx]
        cu_hint = _unique_hint(anchors, "cu_instance_hint")
        if cu_hint is None and e.get("cu_instance_hint") is not None:
            cu_hint = str(e.get("cu_instance_hint"))
        inv_hint = _unique_hint(anchors, "inverter_instance_hint")
        if inv_hint is None and e.get("inverter_instance_hint") is not None:
            inv_hint = str(e.get("inverter_instance_hint"))
        parent_id = None
        basis = None

        opctx = e.get("operator_context", {}) or {}
        if opctx.get("parent_entity_id"):
            parent_id = opctx["parent_entity_id"]
            basis = "OPERATOR_PARENT_CONTEXT"
        elif et in {"MV_LV_TRANSFORMER", "CENTRAL_INVERTER", "IOCB"} and cu_hint is not None:
            cu = cu_by_key.get((e.get("doc"), cu_hint))
            if cu:
                parent_id = cu["entity_id"]
                basis = e.get("membership_basis_hint") or "EXPLICIT_SEMANTIC_CU_INSTANCE_HINT"

        node = {
            "entity_id": e.get("equipment_id"),
            "entity_type": et,
            "source_status": e.get("source_status", "DETECTED"),
            "parent_id": parent_id,
            "membership_basis": basis,
            "children": [],
            "tag": e.get("tag"),
            "cu_instance_hint": cu_hint,
            "inverter_instance_hint": inv_hint,
        }
        nodes[node["entity_id"]] = node
        if et == "CENTRAL_INVERTER" and cu_hint is not None and inv_hint is not None:
            inv_by_key[(e.get("doc"), cu_hint, inv_hint)] = node

    # Second pass: inverter children require inverter identity, not just CU identity.
    for e in equipment:
        et = e.get("equipment_type")
        if et not in {"LV_LV_TRANSFORMER", "STRING_BOX"}:
            continue
        node = nodes.get(e.get("equipment_id"))
        if not node or node.get("parent_id"):
            continue
        anchors = [aidx[x] for x in e.get("anchor_ids", []) if x in aidx]
        cu_hint = _unique_hint(anchors, "cu_instance_hint")
        if cu_hint is None and e.get("cu_instance_hint") is not None:
            cu_hint = str(e.get("cu_instance_hint"))
        inv_hint = _unique_hint(anchors, "inverter_instance_hint")
        if inv_hint is None and e.get("inverter_instance_hint") is not None:
            inv_hint = str(e.get("inverter_instance_hint"))
        opctx = e.get("operator_context", {}) or {}
        if opctx.get("parent_entity_id"):
            node["parent_id"] = opctx["parent_entity_id"]
            node["membership_basis"] = "OPERATOR_PARENT_CONTEXT"
        elif cu_hint is not None and inv_hint is not None:
            inv = inv_by_key.get((e.get("doc"), cu_hint, inv_hint))
            if inv:
                node["parent_id"] = inv["entity_id"]
                node["membership_basis"] = e.get("membership_basis_hint") or "EXPLICIT_SEMANTIC_INVERTER_INSTANCE_HINT"

    for n in list(nodes.values()):
        pid = n.get("parent_id")
        if pid and pid in nodes:
            nodes[pid]["children"].append(n["entity_id"])
        elif n["entity_type"] != "CONVERSION_UNIT" and not pid:
            unresolved_membership.append({
                "entity_id": n["entity_id"],
                "entity_type": n["entity_type"],
                "reason": "NO_RESOLVED_TARGET_PARENT",
            })

    # Derive counts only from resolved children.
    cu_rows = []
    for c in cus:
        cn = nodes[c["entity_id"]]
        children = [nodes[x] for x in cn["children"]]
        inv_rows = []
        for inv in [x for x in children if x["entity_type"] == "CENTRAL_INVERTER"]:
            ich = [nodes[x] for x in inv["children"]]
            inv_rows.append({
                "inverter_id": inv["entity_id"],
                "source_status": inv["source_status"],
                "lv_lv_transformer_count": sum(x["entity_type"] == "LV_LV_TRANSFORMER" for x in ich),
                "string_box_count": sum(x["entity_type"] == "STRING_BOX" for x in ich),
                "lv_lv_transformer_ids": [x["entity_id"] for x in ich if x["entity_type"] == "LV_LV_TRANSFORMER"],
                "string_box_ids": [x["entity_id"] for x in ich if x["entity_type"] == "STRING_BOX"],
            })
        cu_rows.append({
            "conversion_unit_id": c["entity_id"],
            "instance_key": c.get("instance_key"),
            "label": c.get("canonical_label"),
            "source_status": c.get("source_status"),
            "iocb_count": sum(x["entity_type"] == "IOCB" for x in children),
            "mv_lv_transformer_count": sum(x["entity_type"] == "MV_LV_TRANSFORMER" for x in children),
            "inverter_count": len(inv_rows),
            "iocb_ids": [x["entity_id"] for x in children if x["entity_type"] == "IOCB"],
            "mv_lv_transformer_ids": [x["entity_id"] for x in children if x["entity_type"] == "MV_LV_TRANSFORMER"],
            "inverters": inv_rows,
        })

    return {
        "plant_summary": {"conversion_unit_count": len(cu_rows)},
        "conversion_units": cu_rows,
        "nodes": list(nodes.values()),
        "unresolved_membership": unresolved_membership,
        "policy": "COUNTS_DERIVED_ONLY_FROM_RESOLVED_HIERARCHICAL_MEMBERSHIP",
    }
