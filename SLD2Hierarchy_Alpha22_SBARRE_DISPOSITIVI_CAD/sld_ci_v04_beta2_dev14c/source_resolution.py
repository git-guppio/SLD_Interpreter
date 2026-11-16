"""Source/document role resolution for multi-document SLD cases.

A case may contain a primary SLD and an optional plant layout.  Source role is
explicit at the document level; page role is resolved independently of page
position.  No rule assumes that page 1 is an overview.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


SOURCE_SLD = "SLD"
SOURCE_LAYOUT = "LAYOUT"


def normalized_case_key(path_or_name: str) -> str:
    """Return a stable case key from filenames such as PV8_SLD.pdf/PV8_LAYOUT.pdf."""
    stem = Path(path_or_name).stem
    stem = re.sub(r"(?i)(?:[_\-\s]+)(?:SLD|LAYOUT)$", "", stem).strip(" _-")
    return stem or Path(path_or_name).stem


def canonical_plant_id(case_key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", str(case_key)).strip("_") or "UNKNOWN"
    return f"CI::{safe}"


def source_doc_id(plant_id: str, source_role: str) -> str:
    return f"{plant_id}::{source_role.upper()}"


def _cu_instance_hints(page: Dict[str, Any]) -> list[str]:
    vals = []
    for a in page.get("text_equipment_anchors", []) or []:
        if a.get("equipment_type") != "CONVERSION_UNIT":
            continue
        if a.get("anchor_role") not in {"INSTANCE", "TAG"}:
            continue
        v = (a.get("attributes", {}) or {}).get("instance_hint")
        if v is not None:
            vals.append(str(v))
    return vals


def _child_cu_hints(page: Dict[str, Any]) -> list[str]:
    vals = []
    for a in page.get("text_equipment_anchors", []) or []:
        if a.get("anchor_role") not in {"INSTANCE", "TAG"}:
            continue
        v = (a.get("attributes", {}) or {}).get("cu_instance_hint")
        if v is not None:
            vals.append(str(v))
    return vals


def resolve_page_role(page: Dict[str, Any], source_role: str) -> Dict[str, Any]:
    """Resolve page purpose without using ordinal position.

    The explicit document source role is authoritative for LAYOUT documents.
    Within an SLD, a unique local CU or a strongly dominant child-equipment CU
    hint marks a CU detail page.  Otherwise the existing lightweight page type
    remains semantic context only.
    """
    role = str(source_role or SOURCE_SLD).upper()
    if role == SOURCE_LAYOUT:
        page_type = str(page.get("page_type") or "").upper()
        if page.get("mv_circuit_schedule_rows"):
            return {
                "page_role": "MV_CIRCUIT_SCHEDULE",
                "confidence": 0.995,
                "basis": "POSITIONED_EXPLICIT_MV_CIRCUIT_SCHEDULE_ROWS",
            }
        if page_type == "MV_NETWORK_LAYOUT":
            return {
                "page_role": "MV_NETWORK_LAYOUT",
                "confidence": 0.99,
                "basis": "EXPLICIT_LAYOUT_SOURCE_PLUS_MV_NETWORK_TITLE",
            }
        if page_type == "SCHEDULE" and page.get("block_schedule_rows"):
            return {
                "page_role": "CONTAINER_SCHEDULE",
                "confidence": 0.98,
                "basis": "POSITIONED_BLOCK_SCHEDULE_ROWS",
            }
        return {
            "page_role": "PLANT_LAYOUT_OVERVIEW",
            "confidence": 0.95,
            "basis": "EXPLICIT_SOURCE_DOCUMENT_ROLE",
        }

    direct = _cu_instance_hints(page)
    unique = sorted(set(direct))
    if len(unique) == 1:
        return {
            "page_role": "CU_DETAIL",
            "confidence": 0.98,
            "basis": "UNIQUE_LOCAL_CU_INSTANCE",
            "cu_instance_hint": unique[0],
        }

    child = _child_cu_hints(page)
    if child:
        counts = Counter(child)
        winner, n = counts.most_common(1)[0]
        total = sum(counts.values())
        second = counts.most_common(2)[1][1] if len(counts) > 1 else 0
        if n >= 2 and n > second and n / total >= 0.70:
            return {
                "page_role": "CU_DETAIL",
                "confidence": 0.90,
                "basis": "DOMINANT_CHILD_EQUIPMENT_CU_HINT",
                "cu_instance_hint": winner,
            }

    anchors = page.get("text_equipment_anchors", []) or []
    instance_like = sum(a.get("anchor_role") in {"INSTANCE", "TAG"} for a in anchors)
    if page.get("page_type") == "SLD" or instance_like:
        return {
            "page_role": "ELECTRICAL_SLD",
            "confidence": 0.75 if page.get("page_type") == "SLD" else 0.60,
            "basis": "ELECTRICAL_CONTENT_WITHOUT_UNIQUE_CU_SCOPE",
        }

    return {
        "page_role": "OTHER",
        "confidence": 0.50,
        "basis": "NO_STRONG_PAGE_ROLE_EVIDENCE",
    }


def validate_source_pair(sld_path: str, layout_path: Optional[str], plant_id: Optional[str] = None) -> Dict[str, Any]:
    sld_key = normalized_case_key(sld_path)
    layout_key = normalized_case_key(layout_path) if layout_path else None
    mismatch = bool(layout_path and sld_key.upper() != str(layout_key).upper())
    if plant_id:
        resolved_plant_id = plant_id if str(plant_id).startswith("CI::") else canonical_plant_id(str(plant_id))
    else:
        if mismatch:
            raise ValueError(
                f"SLD/layout case keys differ ({sld_key!r} vs {layout_key!r}). "
                "Rename the files consistently or pass --plant-id explicitly."
            )
        resolved_plant_id = canonical_plant_id(sld_key)
    return {
        "plant_id": resolved_plant_id,
        "sld_case_key": sld_key,
        "layout_case_key": layout_key,
        "source_name_consistent": not mismatch,
    }
