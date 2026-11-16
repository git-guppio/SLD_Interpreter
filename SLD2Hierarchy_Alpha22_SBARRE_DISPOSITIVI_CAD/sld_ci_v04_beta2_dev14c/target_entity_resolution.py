"""Resolve indispensable target equipment instances from direct source evidence.

A physical-symbol decision and an asset-instance identity are separate.  An
explicit INSTANCE/TAG text anchor can therefore establish a target equipment
instance even when no reliable local symbol geometry was detected. FAMILY and
CARDINALITY anchors never create instances.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple

TARGET_TYPES = {"IOCB", "MV_LV_TRANSFORMER", "CENTRAL_INVERTER", "LV_LV_TRANSFORMER", "STRING_BOX"}


def _norm_tag(v: Any) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).strip().upper().split())
    return s or None


def _safe(v: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(v).upper()).strip("_")


def _semantic_key(a: Dict[str, Any]) -> Tuple[Any, ...]:
    tag = _norm_tag(a.get("tag"))
    if tag:
        return (a.get("doc"), a.get("equipment_type"), "TAG", tag)
    attrs = a.get("attributes", {}) or {}
    ids = tuple((k, attrs.get(k)) for k in (
        "cu_instance_hint", "inverter_instance_hint", "transformer_instance_hint", "string_box_instance_hint"
    ) if attrs.get(k) is not None)
    if ids:
        return (a.get("doc"), a.get("equipment_type"), "ATTRS", ids)
    # Last-resort explicit instance text, page-scoped to avoid cross-page collapse.
    return (a.get("doc"), a.get("equipment_type"), "TEXT", a.get("page"), _norm_tag(a.get("text")))


def resolve_target_entities(
    pages: List[Dict[str, Any]],
    accepted_equipment: List[Dict[str, Any]],
    supplemental_entities: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    anchors = [a for p in pages for a in p.get("text_equipment_anchors", [])]
    supplemental_entities = list(supplemental_entities or [])
    aidx = {a.get("anchor_id"): a for a in anchors if a.get("anchor_id")}

    # Direct CU instance labels provide page context for diagnosing duplicate/mistag
    # collisions. Context is diagnostic only: it never rewrites a source tag.
    page_cu_context: Dict[Tuple[Any, Any], str] = {}
    for page in pages:
        vals = {
            str((a.get("attributes", {}) or {}).get("instance_hint"))
            for a in page.get("text_equipment_anchors", [])
            if a.get("equipment_type") == "CONVERSION_UNIT"
            and a.get("anchor_role") in {"INSTANCE", "TAG"}
            and (a.get("attributes", {}) or {}).get("instance_hint") is not None
        }
        if len(vals) == 1:
            page_cu_context[(page.get("doc"), page.get("page"))] = next(iter(vals))

    # Accepted physical equipment takes precedence.  Normalize source_status.
    entities: List[Dict[str, Any]] = []
    consumed_anchor_ids = set()
    for e0 in accepted_equipment:
        e = dict(e0)
        e.setdefault("source_status", "DETECTED")
        entities.append(e)
        consumed_anchor_ids.update(e.get("anchor_ids", []))

    buckets: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for a in anchors:
        if a.get("equipment_type") not in TARGET_TYPES:
            continue
        if a.get("anchor_role") not in {"INSTANCE", "TAG"}:
            continue
        if a.get("anchor_id") in consumed_anchor_ids:
            continue
        buckets[_semantic_key(a)].append(a)

    source_instance_collisions: List[Dict[str, Any]] = []
    for key, items in sorted(buckets.items(), key=lambda kv: repr(kv[0])):
        if len(items) <= 1:
            continue
        occurrences = []
        context_conflict = False
        for a in items:
            attrs = a.get("attributes", {}) or {}
            parsed_cu = attrs.get("cu_instance_hint")
            page_cu = page_cu_context.get((a.get("doc"), a.get("page")))
            conflict = parsed_cu is not None and page_cu is not None and str(parsed_cu) != str(page_cu)
            context_conflict = context_conflict or conflict
            occurrences.append({
                "page": a.get("page"),
                "anchor_id": a.get("anchor_id"),
                "text": a.get("text"),
                "tag": a.get("tag"),
                "parsed_cu_instance_hint": parsed_cu,
                "page_cu_context": page_cu,
                "context_conflict": conflict,
                "bbox": a.get("bbox"),
            })
        source_instance_collisions.append({
            "semantic_key": repr(key),
            "equipment_type": items[0].get("equipment_type"),
            "tag": _norm_tag(items[0].get("tag")),
            "occurrence_count": len(items),
            "pages": sorted({a.get("page") for a in items if a.get("page") is not None}),
            "status": "POSSIBLE_MISTAG_OR_DUPLICATE_INSTANCE" if context_conflict else "REPEATED_SOURCE_INSTANCE",
            "context_conflict": context_conflict,
            "occurrences": occurrences,
            "policy": "DIAGNOSTIC_ONLY_NO_AUTOMATIC_TAG_CORRECTION",
        })

    for idx, (key, items) in enumerate(sorted(buckets.items(), key=lambda kv: repr(kv[0])), start=1):
        typ = items[0].get("equipment_type")
        tag = next((_norm_tag(a.get("tag")) for a in items if _norm_tag(a.get("tag"))), None)
        eid_core = _safe(tag) if tag else f"SEM_{idx:05d}"
        doc = items[0].get("doc")
        entities.append({
            "equipment_id": f"{doc}::{typ}::{eid_core}",
            "equipment_type": typ,
            "doc": doc,
            "tag": tag,
            "source_symbol_ids": [],
            "occurrences": [
                {"page": a.get("page"), "bbox": a.get("bbox"), "anchor_id": a.get("anchor_id")}
                for a in items
            ],
            "anchor_ids": [a.get("anchor_id") for a in items if a.get("anchor_id")],
            "acceptance_reason": "EXPLICIT_SOURCE_INSTANCE_OR_TAG_WITHOUT_REQUIRED_GEOMETRY",
            "confidence": min(float(a.get("confidence", 1.0)) for a in items),
            "source_status": "DETECTED",
            "evidence_mode": "SEMANTIC_INSTANCE",
        })

    # Add evidence-resolved supplemental entities after explicit source instances.
    # Explicit accepted/source-tagged entities keep precedence; supplemental
    # inference is expected to have been de-duplicated by its own resolver.
    existing_ids = {e.get("equipment_id") for e in entities}
    for e in supplemental_entities:
        if e.get("equipment_id") and e.get("equipment_id") not in existing_ids:
            entities.append(dict(e))
            existing_ids.add(e.get("equipment_id"))

    counts = defaultdict(int)
    for e in entities:
        if e.get("equipment_type") in TARGET_TYPES:
            counts[e["equipment_type"]] += 1

    raw_source_instance_counts = defaultdict(int)
    for a in anchors:
        if a.get("equipment_type") in TARGET_TYPES and a.get("anchor_role") in {"INSTANCE", "TAG"}:
            raw_source_instance_counts[a.get("equipment_type")] += 1

    return {
        "entities": entities,
        "counts": dict(counts),
        "raw_source_instance_counts": dict(raw_source_instance_counts),
        "source_instance_collisions": source_instance_collisions,
        "identity_resolution_complete": not any(x.get("context_conflict") for x in source_instance_collisions),
    }
