"""Create conservative resolution requests for indispensable target data."""
from __future__ import annotations
from typing import Any, Dict, List
from .resolution_models import ResolutionRequest


def build_resolution_requests(
    pages: List[Dict[str, Any]],
    feature_profiles: List[Dict[str, Any]],
    accepted_equipment: List[Dict[str, Any]],
    container_resolution: Dict[str, Any] | None = None,
    operator_feedback: List[Dict[str, Any]] | None = None,
    target_hierarchy: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    requests: List[ResolutionRequest] = []
    operator_feedback = list(operator_feedback or [])
    answered = {fb.get("request_id") for fb in operator_feedback if fb.get("request_id")}
    docs = sorted({p.get("doc") for p in pages if p.get("doc")})
    resolved_cu_docs = {e.get("doc") for e in (container_resolution or {}).get("entities", [])}
    target_hierarchy = target_hierarchy or {}

    # Resolved target counts are hierarchy-derived, never candidate-derived.
    target_cus = list(target_hierarchy.get("conversion_units", []) or [])
    resolved_mv_lv_count = sum(int(c.get("mv_lv_transformer_count") or 0) for c in target_cus)
    resolved_lv_lv_count = sum(
        int(inv.get("lv_lv_transformer_count") or 0)
        for c in target_cus for inv in (c.get("inverters", []) or [])
    )

    for doc in docs:
        anchors = [a for p in pages if p.get("doc") == doc for a in p.get("text_equipment_anchors", [])]
        cu_anchors = [a for a in anchors if a.get("equipment_type") == "CONVERSION_UNIT"]
        cu_with_id = [a for a in cu_anchors if a.get("attributes", {}).get("instance_hint") is not None]
        accepted_cu = [e for e in accepted_equipment if e.get("doc") == doc and e.get("equipment_type") == "CONVERSION_UNIT"]
        req_id = f"{doc}::REQ::CU_IDENTIFIER"

        if cu_anchors and not cu_with_id and not accepted_cu and doc not in resolved_cu_docs and req_id not in answered:
            values = sorted({a.get("text") for a in cu_anchors if a.get("text")})[:12]
            requests.append(ResolutionRequest(
                request_id=req_id,
                target="CONVERSION_UNIT_INSTANCE_IDENTIFIER",
                reason="CU_FAMILY_EVIDENCE_WITHOUT_RELIABLE_INSTANCE_DISCRIMINATOR",
                doc=doc,
                candidate_values=values,
                interaction_mode="PROVIDE_VALUE",
                context={"anchor_ids": [a.get("anchor_id") for a in cu_anchors]},
            ))

        # Apparent-power ratings (kVA/MVA) are independent semantic evidence
        # that a power device is represented. They never auto-classify a
        # transformer, but if no transformer has been resolved they create a
        # document-level visual resolution request.
        rating_anchors = [
            a for a in anchors
            if a.get("equipment_type") == "TRANSFORMER_CANDIDATE"
            and a.get("anchor_role") == "RATING"
            and a.get("evidence_kind") == "APPARENT_POWER_RATING"
        ]
        rating_req_id = f"{doc}::REQ::TRANSFORMER_RATING_EVIDENCE"
        if rating_anchors and (resolved_mv_lv_count + resolved_lv_lv_count) == 0 and rating_req_id not in answered:
            visual_hints = [
                {
                    "group_id": f"ANCHOR::{a.get('anchor_id')}",
                    "page": a.get("page"),
                    "bbox": a.get("bbox"),
                    "candidate_type": "APPARENT_POWER_RATING_EVIDENCE",
                    "rating_text": a.get("text"),
                    "anchor_id": a.get("anchor_id"),
                }
                for a in rating_anchors if a.get("bbox") and a.get("page") is not None
            ]
            pages_involved = sorted({x.get("page") for x in visual_hints if x.get("page") is not None})
            requests.append(ResolutionRequest(
                request_id=rating_req_id,
                target="TARGET_TRANSFORMER_VISUAL_OR_SEMANTIC_CLASSIFICATION",
                reason="APPARENT_POWER_RATING_EVIDENCE_WITHOUT_RESOLVED_TRANSFORMER",
                doc=doc,
                page=pages_involved[0] if len(pages_involved) == 1 else None,
                interaction_mode="VISUAL_SELECT",
                context={
                    "allowed_target_classes": ["MV_LV_TRANSFORMER", "LV_LV_TRANSFORMER", "OTHER_ELECTRICAL"],
                    "operator_options": ["SELECT_DEVICE", "NOT_REPRESENTED_IN_SLD", "UNABLE_TO_IDENTIFY"],
                    "visual_hints": visual_hints,
                    "pages_involved": pages_involved,
                    "evidence_role": "RATING_ONLY_DOES_NOT_AUTO_CLASSIFY",
                    "note": "Select the actual device, not the rating text. If no detector candidate overlaps the selection, the run records DETECTION_FAILURE for detector improvement.",
                },
            ))

        generic_groups = [
            p for p in feature_profiles
            if p.get("document") == doc
            and p.get("candidate_type") == "PAIRED_CIRCLE_ELECTRICAL_CANDIDATE"
            and p.get("scope_status") != "OUT_OF_SCOPE"
        ]
        req_id = f"{doc}::REQ::GENERIC_PAIRED_CIRCLE"
        if generic_groups and req_id not in answered:
            visual_hints = [
                {
                    "group_id": p.get("group_id"),
                    "page": p.get("page"),
                    "bbox": (p.get("geometry") or {}).get("bbox"),
                    "candidate_type": p.get("candidate_type"),
                    "morph_family_id": (p.get("repetition") or {}).get("morph_family_id"),
                    "family_size": (p.get("repetition") or {}).get("family_size"),
                    "terminal_count": (p.get("topology") or {}).get("terminal_count"),
                }
                for p in generic_groups
            ]
            pages_involved = sorted({x.get("page") for x in visual_hints if x.get("page") is not None})
            requests.append(ResolutionRequest(
                request_id=req_id,
                target="TARGET_TRANSFORMER_VISUAL_OR_SEMANTIC_CLASSIFICATION",
                reason="GENERIC_GEOMETRY_REQUIRES_TARGET_CLASSIFICATION",
                doc=doc,
                page=pages_involved[0] if len(pages_involved) == 1 else None,
                group_ids=[p["group_id"] for p in generic_groups],
                interaction_mode="VISUAL_SELECT",
                context={
                    "allowed_target_classes": ["MV_LV_TRANSFORMER", "LV_LV_TRANSFORMER", "OTHER_ELECTRICAL"],
                    "operator_options": ["SELECT_DEVICE", "NOT_REPRESENTED_IN_SLD", "UNABLE_TO_IDENTIFY"],
                    "visual_hints": visual_hints,
                    "pages_involved": pages_involved,
                    "note": "Operator selection is accepted for current run with OPERATOR_PROVIDED provenance.",
                },
            ))

    return [r.to_dict() for r in requests]
