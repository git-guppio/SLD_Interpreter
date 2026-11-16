"""Compact resolved-target summary for operator-facing CLI output.

Raw symbol/candidate counts are intentionally kept separate from resolved
asset counts.  The latter are derived only from ``target_hierarchy``.
"""
from __future__ import annotations
from typing import Any, Dict


def summarize_target_hierarchy(target_hierarchy: Dict[str, Any]) -> Dict[str, Any]:
    cus = list((target_hierarchy or {}).get("conversion_units", []) or [])
    inverters = [inv for cu in cus for inv in (cu.get("inverters", []) or [])]
    return {
        "conversion_units": len(cus),
        "iocb": sum(int(cu.get("iocb_count") or 0) for cu in cus),
        "mv_lv_transformers": sum(int(cu.get("mv_lv_transformer_count") or 0) for cu in cus),
        "inverters": len(inverters),
        "lv_lv_transformers": sum(int(inv.get("lv_lv_transformer_count") or 0) for inv in inverters),
        "string_boxes": sum(int(inv.get("string_box_count") or 0) for inv in inverters),
        "unresolved_membership": len((target_hierarchy or {}).get("unresolved_membership", []) or []),
        "count_policy": "RESOLVED_HIERARCHICAL_MEMBERSHIP_ONLY",
    }
