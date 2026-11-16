"""UI-agnostic operator interaction contract.

The same records can be produced by CLI, tests, or a future PDF visual annotator.
Operator input is accepted for the current run, but provenance always remains
OPERATOR_PROVIDED.
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List

VALID_OPTIONS = {"SELECT_DEVICE", "NOT_REPRESENTED_IN_SLD", "UNABLE_TO_IDENTIFY", "PROVIDE_VALUE", "CONFIRM_CANDIDATE"}
TARGET_CLASSES = {"CONVERSION_UNIT", "IOCB", "MV_LV_TRANSFORMER", "CENTRAL_INVERTER", "LV_LV_TRANSFORMER", "STRING_BOX", "OTHER_ELECTRICAL"}
RESOLUTION_TARGETS = {
    "CONVERSION_UNIT_INSTANCE_IDENTIFIER",
    "TARGET_DEVICE_VISUAL_CLASSIFICATION",
    "TARGET_TRANSFORMER_VISUAL_OR_SEMANTIC_CLASSIFICATION",
    "IOCB_IDENTIFIER",
    "INVERTER_IDENTIFIER",
    "STRING_BOX_IDENTIFIER",
    "PARENT_MEMBERSHIP",
    "MV_LINE_LABEL_MAPPING",
    "FEEDER_ELECTRICAL_PATH_VERIFICATION",
}


def validate_feedback(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    out.setdefault("status", "OPERATOR_PROVIDED")
    if out["status"] != "OPERATOR_PROVIDED":
        raise ValueError("Operator feedback must keep OPERATOR_PROVIDED provenance")

    target = out.get("target")
    if target is not None and target not in RESOLUTION_TARGETS:
        raise ValueError(f"Unsupported resolution target: {target}")

    option = out.get("option")
    if option is not None and option not in VALID_OPTIONS:
        raise ValueError(f"Unsupported operator option: {option}")

    dtype = out.get("device_type")
    if dtype is not None and dtype not in TARGET_CLASSES:
        raise ValueError(f"Unsupported target class: {dtype}")

    if option == "SELECT_DEVICE":
        if not out.get("bbox") and not out.get("group_id"):
            raise ValueError("SELECT_DEVICE requires bbox or group_id")
        if out.get("page") is None:
            raise ValueError("SELECT_DEVICE requires page")
        if dtype is None:
            raise ValueError("SELECT_DEVICE requires device_type")

    if target == "CONVERSION_UNIT_INSTANCE_IDENTIFIER" and out.get("value") is None:
        raise ValueError("CONVERSION_UNIT_INSTANCE_IDENTIFIER requires value")

    if target == "MV_LINE_LABEL_MAPPING":
        if option != "PROVIDE_VALUE":
            raise ValueError("MV_LINE_LABEL_MAPPING requires option=PROVIDE_VALUE")
        value = out.get("value")
        if not isinstance(value, dict) or not value:
            raise ValueError("MV_LINE_LABEL_MAPPING requires a non-empty mapping object")
        cleaned = {}
        for key, label in value.items():
            sk = str(key).strip()
            lab = str(label).strip()
            if not sk or not lab:
                raise ValueError("MV_LINE_LABEL_MAPPING keys and labels must be non-empty")
            cleaned[sk] = lab
        out["value"] = cleaned

    if target == "FEEDER_ELECTRICAL_PATH_VERIFICATION":
        if option != "PROVIDE_VALUE":
            raise ValueError("FEEDER_ELECTRICAL_PATH_VERIFICATION requires option=PROVIDE_VALUE")
        value = out.get("value")
        if not isinstance(value, dict):
            raise ValueError("FEEDER_ELECTRICAL_PATH_VERIFICATION requires a value object")
        action = value.get("action")
        if action not in {"BIND_XFR_MV_TERMINAL_PATTERN", "BIND_FEEDER_ROOT_PATTERN", "ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN", "ADD_FEEDER_GRAPH_BRIDGE_INSTANCE", "CLASSIFY_FEEDER_BREAKPOINT"}:
            raise ValueError(f"Unsupported feeder verification action: {action}")
        if action == "BIND_XFR_MV_TERMINAL_PATTERN":
            off = value.get("offset_from_tag_center_pt")
            if not (isinstance(off, (list, tuple)) and len(off) == 2):
                raise ValueError("BIND_XFR_MV_TERMINAL_PATTERN requires offset_from_tag_center_pt")
        if action == "BIND_FEEDER_ROOT_PATTERN":
            off = value.get("offset_from_line_anchor_center_pt")
            if not (isinstance(off, (list, tuple)) and len(off) == 2):
                raise ValueError("BIND_FEEDER_ROOT_PATTERN requires offset_from_line_anchor_center_pt")
        if action == "ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN":
            if value.get("orientation") not in {"H", "V"} or not value.get("gap_length_pt"):
                raise ValueError("ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN requires orientation and gap_length_pt")
        if action == "ADD_FEEDER_GRAPH_BRIDGE_INSTANCE":
            if not (value.get("point_a") and value.get("point_b") and value.get("page") is not None):
                raise ValueError("ADD_FEEDER_GRAPH_BRIDGE_INSTANCE requires page, point_a and point_b")
        if action == "CLASSIFY_FEEDER_BREAKPOINT":
            cls = str(value.get("classification") or "").upper()
            if cls not in {"CONDUCTIVE_CONTINUITY", "INTERPOSED_DEVICE", "NON_ELECTRICAL_GRAPHIC", "UNRESOLVED"}:
                raise ValueError("CLASSIFY_FEEDER_BREAKPOINT requires a supported classification")
            if not (value.get("point_a") and value.get("point_b") and value.get("page") is not None):
                raise ValueError("CLASSIFY_FEEDER_BREAKPOINT requires page, point_a and point_b")
            if value.get("source_node_id") is None or value.get("target_node_id") is None:
                raise ValueError("CLASSIFY_FEEDER_BREAKPOINT requires source_node_id and target_node_id")
            if cls == "INTERPOSED_DEVICE" and not value.get("device_type"):
                value["device_type"] = "UNDETERMINED"

    return out


def validate_feedback_batch(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [validate_feedback(r) for r in records]
