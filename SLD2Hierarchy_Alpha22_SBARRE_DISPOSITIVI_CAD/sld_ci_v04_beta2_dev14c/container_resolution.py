"""Resolve Conversion Unit containers independently from physical symbols.

The resolver is deliberately conservative:
- text INSTANCE/TAG evidence can create CU entities;
- repeated references to the same explicit instance are reconciled;
- learned identifier patterns can add CU evidence only when they match source text;
- operator-provided container identifiers are accepted for the current run with
  explicit OPERATOR_PROVIDED provenance;
- no graphical proximity is used here to assign child equipment.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _norm(s: Any) -> str:
    return " ".join(str(s or "").strip().upper().split())


def _instance_from_anchor(anchor: Dict[str, Any]) -> Optional[str]:
    attrs = anchor.get("attributes", {}) or {}
    v = attrs.get("instance_hint")
    if v is None:
        return None
    return str(v)


def _entity_id(doc: str, instance_key: str) -> str:
    safe = re.sub(r"[^A-Z0-9]+", "_", _norm(instance_key)).strip("_") or "UNKNOWN"
    return f"{doc}::CU::{safe}"


def _compile_learned_pattern(pattern: Dict[str, Any]) -> Optional[re.Pattern[str]]:
    """Compile only explicitly stored regex patterns; never invent semantics here."""
    raw = pattern.get("regex") or pattern.get("pattern")
    if not raw:
        return None
    if pattern.get("pattern_format") not in {None, "REGEX"}:
        return None
    try:
        return re.compile(str(raw), re.I)
    except re.error:
        return None


def resolve_conversion_units(
    pages: List[Dict[str, Any]],
    learned_patterns: Optional[Iterable[Dict[str, Any]]] = None,
    operator_feedback: Optional[Iterable[Dict[str, Any]]] = None,
    supplemental_entities: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    learned_patterns = list(learned_patterns or [])
    operator_feedback = list(operator_feedback or [])
    supplemental_entities = list(supplemental_entities or [])

    evidence: List[Dict[str, Any]] = []

    # 1) Direct source evidence.  Only INSTANCE/TAG anchors with explicit IDs
    # create entities. FAMILY/CARDINALITY stay evidence only.
    for page in pages:
        for a in page.get("text_equipment_anchors", []):
            if a.get("equipment_type") != "CONVERSION_UNIT":
                continue
            inst = _instance_from_anchor(a)
            evidence.append({
                "doc": a.get("doc") or page.get("doc"),
                "page": a.get("page") or page.get("page"),
                "text": a.get("text"),
                "anchor_id": a.get("anchor_id"),
                "anchor_role": a.get("anchor_role"),
                "instance_key": inst,
                "source_status": "DETECTED",
                "evidence_kind": a.get("evidence_kind"),
                "confidence": a.get("confidence"),
            })

    # 2) Learned lexical patterns may identify an instance from raw page text
    # already extracted into semantic anchors. They never override direct source
    # evidence and remain INFERRED with pattern provenance.
    cu_patterns = [
        p for p in learned_patterns
        if p.get("pattern_type") == "IDENTIFIER_PATTERN"
        and p.get("entity_type") == "CONVERSION_UNIT"
        and p.get("enabled", True)
    ]
    for pattern in cu_patterns:
        rx = _compile_learned_pattern(pattern)
        if rx is None:
            continue
        for page in pages:
            doc = page.get("doc")
            # Search all text anchor strings, not only CU anchors, because the
            # point of operator teaching may be to introduce a previously unknown alias.
            texts = []
            for a in page.get("text_equipment_anchors", []):
                if a.get("text"):
                    texts.append((a.get("text"), a.get("anchor_id")))
            for text, anchor_id in texts:
                for m in rx.finditer(text):
                    gd = m.groupdict()
                    inst = gd.get("id") or gd.get("instance")
                    if inst is None and m.lastindex:
                        inst = m.group(1)
                    if inst is None:
                        continue
                    # Skip if direct detected evidence already carries this doc/page/instance.
                    if any(e["doc"] == doc and e["page"] == page.get("page") and e.get("instance_key") == str(inst)
                           and e["source_status"] == "DETECTED" for e in evidence):
                        continue
                    evidence.append({
                        "doc": doc,
                        "page": page.get("page"),
                        "text": m.group(0),
                        "anchor_id": anchor_id,
                        "anchor_role": "LEARNED_IDENTIFIER",
                        "instance_key": str(inst),
                        "source_status": "INFERRED",
                        "evidence_kind": "LEARNED_IDENTIFIER_PATTERN",
                        "confidence": None,
                        "pattern_id": pattern.get("pattern_id"),
                    })

    # 3) Operator-provided explicit CU identifiers are valid for current run.
    # Expected feedback record: target=CONVERSION_UNIT_INSTANCE_IDENTIFIER and
    # value can be a scalar or a list of {instance_key,label,page?} mappings.
    for fb in operator_feedback:
        if fb.get("status") != "OPERATOR_PROVIDED":
            continue
        if fb.get("target") != "CONVERSION_UNIT_INSTANCE_IDENTIFIER":
            continue
        doc = fb.get("doc")
        raw = fb.get("value")
        vals = raw if isinstance(raw, list) else [raw]
        for item in vals:
            if isinstance(item, dict):
                inst = item.get("instance_key") or item.get("id") or item.get("value")
                label = item.get("label") or inst
                page_no = item.get("page")
            else:
                inst = item
                label = item
                page_no = fb.get("page")
            if inst is None or doc is None:
                continue
            evidence.append({
                "doc": doc,
                "page": page_no,
                "text": str(label),
                "anchor_id": None,
                "anchor_role": "OPERATOR_PROVIDED",
                "instance_key": str(inst),
                "source_status": "OPERATOR_PROVIDED",
                "evidence_kind": "OPERATOR_CU_IDENTIFIER",
                "confidence": None,
                "feedback_id": fb.get("feedback_id") or fb.get("request_id"),
            })

    buckets: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    unresolved_family_evidence: List[Dict[str, Any]] = []
    for e in evidence:
        if e.get("instance_key") is None:
            unresolved_family_evidence.append(e)
            continue
        buckets[(e["doc"], str(e["instance_key"]))].append(e)

    entities = []
    precedence = {"DETECTED": 3, "OPERATOR_PROVIDED": 2, "INFERRED": 1}
    for (doc, inst), items in sorted(buckets.items()):
        best_status = max((i["source_status"] for i in items), key=lambda s: precedence.get(s, 0))
        labels = []
        for i in items:
            if i.get("text") and i["text"] not in labels:
                labels.append(i["text"])
        entities.append({
            "entity_id": _entity_id(doc, inst),
            "entity_type": "CONVERSION_UNIT",
            "doc": doc,
            "instance_key": inst,
            "canonical_label": labels[0] if labels else f"CU {inst}",
            "source_status": best_status,
            "source_labels": labels,
            "representations": [
                {
                    "page": i.get("page"),
                    "text": i.get("text"),
                    "anchor_id": i.get("anchor_id"),
                    "representation_role": (
                        "OPERATOR_PROVIDED" if i["source_status"] == "OPERATOR_PROVIDED"
                        else "SOURCE_INSTANCE" if i.get("anchor_role") in {"INSTANCE", "TAG"}
                        else "LEARNED_INSTANCE"
                    ),
                    "source_status": i["source_status"],
                    "pattern_id": i.get("pattern_id"),
                }
                for i in items
            ],
        })

    # 4) Cross-source/document-local supplemental CU models may add INFERRED
    # containers.  They never override direct source or operator evidence.
    by_entity_key = {(str(e.get("doc")), str(e.get("instance_key"))): e for e in entities}
    for sup0 in supplemental_entities:
        sup = dict(sup0)
        if sup.get("entity_type") != "CONVERSION_UNIT" or sup.get("instance_key") is None:
            continue
        key = (str(sup.get("doc")), str(sup.get("instance_key")))
        if key in by_entity_key:
            cur = by_entity_key[key]
            for label in sup.get("source_labels", []) or []:
                if label not in cur.setdefault("source_labels", []):
                    cur["source_labels"].append(label)
            cur.setdefault("representations", []).extend(sup.get("representations", []) or [])
            cur.setdefault("supplemental_inference", []).append({
                "source_status": sup.get("source_status", "INFERRED"),
                "inference_basis": sup.get("inference_basis"),
            })
            continue
        sup.setdefault("source_status", "INFERRED")
        sup.setdefault("canonical_label", f"CU {sup.get('instance_key')}")
        sup.setdefault("source_labels", [])
        sup.setdefault("representations", [])
        entities.append(sup)
        by_entity_key[key] = sup

    entities.sort(key=lambda e: (str(e.get("doc")), not str(e.get("instance_key")).isdigit(), int(e.get("instance_key")) if str(e.get("instance_key")).isdigit() else str(e.get("instance_key"))))

    return {
        "entities": entities,
        "unresolved_family_evidence": unresolved_family_evidence,
        "summary": {
            "conversion_unit_count": len(entities),
            "detected_count": sum(e.get("source_status") == "DETECTED" for e in entities),
            "operator_provided_count": sum(e.get("source_status") == "OPERATOR_PROVIDED" for e in entities),
            "inferred_count": sum(e.get("source_status") == "INFERRED" for e in entities),
        },
    }
