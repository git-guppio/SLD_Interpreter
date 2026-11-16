"""Conservative rule induction from operator feedback.

Only lexical CU identifier examples are generalized in dev2.  Visual geometry
feedback is stored as labelled evidence but is *not* automatically generalized
into an equipment-class rule.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _derive_simple_regex(labels: List[str]) -> Optional[str]:
    labels = [str(x).strip() for x in labels if str(x).strip()]
    if len(labels) < 2:
        return None
    # Prefix + numeric identifier + suffix, same fixed parts across examples.
    parsed: List[Tuple[str, str, str]] = []
    for s in labels:
        m = re.match(r"^(.*?)(\d+)(\D*)$", s)
        if not m:
            return None
        parsed.append(m.groups())
    prefixes = {p for p, _, _ in parsed}
    suffixes = {s for _, _, s in parsed}
    if len(prefixes) != 1 or len(suffixes) != 1:
        return None
    prefix = next(iter(prefixes))
    suffix = next(iter(suffixes))
    return rf"\b{re.escape(prefix)}(?P<id>\d+){re.escape(suffix)}\b"


def patterns_from_feedback(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fb in records:
        if fb.get("status") != "OPERATOR_PROVIDED":
            continue
        target = fb.get("target")
        if target == "CONVERSION_UNIT_INSTANCE_IDENTIFIER":
            raw = fb.get("value")
            vals = raw if isinstance(raw, list) else [raw]
            labels = []
            for item in vals:
                if isinstance(item, dict):
                    label = item.get("label") or item.get("value") or item.get("instance_key")
                else:
                    label = item
                if label is not None:
                    labels.append(str(label))
            regex = _derive_simple_regex(labels)
            if regex:
                out.append({
                    "pattern_type": "IDENTIFIER_PATTERN",
                    "entity_type": "CONVERSION_UNIT",
                    "pattern": regex,
                    "regex": regex,
                    "pattern_format": "REGEX",
                    "scope": fb.get("learning_scope", "GENERAL"),
                    "origin": "OPERATOR_PROVIDED",
                    "origin_document": fb.get("doc"),
                    "examples": labels,
                })
            continue

        if target == "MV_LINE_LABEL_MAPPING":
            mapping = fb.get("value")
            if isinstance(mapping, dict) and mapping:
                # Deliberately plant-scoped: a left-to-right feeder order taught
                # on one plant must not silently become a global convention.
                import json
                plant_id = fb.get("plant_id") or (fb.get("context", {}) or {}).get("plant_id")
                out.append({
                    "pattern_type": "MV_LINE_LABEL_MAPPING",
                    "entity_type": "MV_LINE",
                    "pattern": json.dumps(mapping, sort_keys=True, ensure_ascii=False),
                    "mapping": {str(k): str(v) for k, v in mapping.items()},
                    "pattern_format": "MAPPING",
                    "scope": fb.get("learning_scope", "PLANT"),
                    "origin": "OPERATOR_PROVIDED",
                    "origin_document": fb.get("doc"),
                    "origin_plant_id": plant_id,
                    "context_signature": {
                        "feeder_count": len(mapping),
                        "source_role": "LAYOUT",
                    },
                })
            continue

        if target == "FEEDER_ELECTRICAL_PATH_VERIFICATION":
            value = fb.get("value")
            if not isinstance(value, dict):
                continue
            action = value.get("action")
            plant_id = fb.get("plant_id") or (fb.get("context", {}) or {}).get("plant_id")
            import json
            if action == "BIND_XFR_MV_TERMINAL_PATTERN":
                payload = {
                    "offset_from_tag_center_pt": value.get("offset_from_tag_center_pt"),
                    "max_snap_distance_pt": value.get("max_snap_distance_pt", 32.0),
                }
                out.append({
                    "pattern_type": "XFR_MV_TERMINAL_BINDING_PATTERN",
                    "entity_type": "MV_LV_TRANSFORMER",
                    "pattern": json.dumps(payload, sort_keys=True),
                    **payload,
                    "pattern_format": "GEOMETRIC_OFFSET",
                    "scope": "PLANT",
                    "origin": "OPERATOR_PROVIDED",
                    "origin_document": fb.get("doc"),
                    "origin_plant_id": plant_id,
                    "examples": [value.get("xfr_instance_key")],
                })
            elif action == "BIND_FEEDER_ROOT_PATTERN":
                payload = {
                    "offset_from_line_anchor_center_pt": value.get("offset_from_line_anchor_center_pt"),
                    "anchor_style": value.get("anchor_style"),
                    "max_snap_distance_pt": value.get("max_snap_distance_pt", 36.0),
                }
                out.append({
                    "pattern_type": "FEEDER_ROOT_BINDING_PATTERN",
                    "entity_type": "MV_LINE",
                    "pattern": json.dumps(payload, sort_keys=True),
                    **payload,
                    "pattern_format": "GEOMETRIC_OFFSET",
                    "scope": "PLANT",
                    "origin": "OPERATOR_PROVIDED",
                    "origin_document": fb.get("doc"),
                    "origin_plant_id": plant_id,
                    "examples": [value.get("feeder_id")],
                })
            elif action == "ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN":
                payload = {
                    "orientation": value.get("orientation"),
                    "gap_length_pt": value.get("gap_length_pt"),
                    "axis_tolerance_pt": value.get("axis_tolerance_pt"),
                    "gap_tolerance_pt": value.get("gap_tolerance_pt"),
                    "context_class": value.get("context_class", "XFR_MV_TERMINAL_NEIGHBORHOOD"),
                    "focus_radius_pt": value.get("focus_radius_pt", 48.0),
                }
                out.append({
                    "pattern_type": "CONDUCTIVE_GAP_BRIDGE_PATTERN",
                    "entity_type": "ELECTRICAL_CONNECTIVITY",
                    "pattern": json.dumps(payload, sort_keys=True),
                    **payload,
                    "pattern_format": "GEOMETRIC_GAP",
                    "scope": "PLANT",
                    "origin": "OPERATOR_PROVIDED",
                    "origin_document": fb.get("doc"),
                    "origin_plant_id": plant_id,
                    "safety_policy": "CONDUCTIVE_INLINE_GAP_ONLY__NEVER_TRANSFORMER_WINDINGS",
                })
            continue
    return out
