"""Conservative domain acceptance.

Cardinality never creates equipment.
Generic geometric families remain unresolved until independent semantic
evidence supports a physical equipment classification.
"""

from .equipment_consolidation import overlap


ACCEPTABLE = {
    "CENTRAL_INVERTER",
    "MV_LV_TRANSFORMER",
    "CONVERSION_UNIT",
    "STRING_BOX",
}

GENERIC_GEOMETRY_TYPES = {
    "PAIRED_CIRCLE_ELECTRICAL_CANDIDATE",
}


def decide_equipment(groups):
    accepted, decisions = [], []

    for g in groups:
        geometric = [
            s
            for s in g["members"]
            if s["evidence_state"] != "TEXT_ONLY"
        ]

        terminal_members = [
            s
            for s in geometric
            if s.get("terminals")
        ]

        instance_anchors = [
            a
            for a in g["anchors"]
            if a.get("anchor_role") in {"INSTANCE", "TAG"}
            and a["equipment_type"] in ACCEPTABLE
        ]

        strong = [
            a
            for a in instance_anchors
            if any(
                s.get("text_anchor_id") == a["anchor_id"]
                and s["evidence_state"] == "FUSED"
                and s.get("terminals")
                and (
                    a["equipment_type"] != "CENTRAL_INVERTER"
                    or s.get("geometry_kind") == "RECTANGLE_WITH_DIAGONAL"
                    or s.get("evidence", {}).get("has_internal_diagonal")
                )
                for s in geometric
            )
        ]

        kind = strong[0]["equipment_type"] if strong else None
        reason = "EXPLICIT_TEXT_COMPATIBLE_GEOMETRY_AND_TERMINALS"

        if len({a["equipment_type"] for a in strong}) > 1:
            kind = None
            reason = "CONFLICTING_EQUIPMENT_TYPES"

        if not kind:
            refs = [
                s
                for s in geometric
                if s.get("evidence", {}).get("scale_status") == "REFERENCE"
                and s.get("evidence", {}).get("has_internal_diagonal")
            ]

            if any(
                overlap(r["bbox"], t["bbox"]) >= 0.85
                for r in refs
                for t in terminal_members
            ):
                kind = "CENTRAL_INVERTER"
                reason = (
                    "LOCAL_FAMILY_REFERENCE_CONVERTER_GEOMETRY_AND_TERMINALS"
                )

        # Generic geometry must remain unresolved until semantic evidence
        # independently identifies the physical equipment family.
        generic_types = {
            s.get("candidate_type")
            for s in geometric
            if s.get("candidate_type") in GENERIC_GEOMETRY_TYPES
        }

        if (
            not kind
            and generic_types
            and terminal_members
        ):
            decisions.append(
                {
                    "group_id": g["group_id"],
                    "status": "UNRESOLVED",
                    "reason": "GENERIC_GEOMETRY_REQUIRES_SEMANTIC_CLASSIFICATION",
                    "candidate_types": sorted(generic_types),
                    "terminal_member_count": len(terminal_members),
                }
            )
            continue

        if not kind or g["scope_status"] != "IN_SCOPE":
            decisions.append(
                {
                    "group_id": g["group_id"],
                    "status": "UNRESOLVED",
                    "reason": (
                        reason
                        if reason.startswith("CONFLICT")
                        else "NO_INDEPENDENT_PHYSICAL_AND_SEMANTIC_SUPPORT"
                    ),
                }
            )
            continue

        tag_anchors = [
            a
            for a in strong
            if a.get("anchor_role") == "TAG"
        ]

        tag = (
            tag_anchors[0]["tag"].upper()
            if tag_anchors
            else None
        )

        accepted.append(
            {
                "equipment_id": g["group_id"] + "_EQ",
                "equipment_type": kind,
                "doc": g["doc"],
                "tag": tag,
                "source_symbol_ids": [
                    s["symbol_id"]
                    for s in g["members"]
                ],
                "occurrences": [
                    {
                        "page": g["page"],
                        "bbox": s["bbox"],
                        "symbol_id": s["symbol_id"],
                    }
                    for s in terminal_members
                ],
                "anchor_ids": [
                    a["anchor_id"]
                    for a in g["anchors"]
                ],
                "acceptance_reason": reason,
                "confidence": min(
                    [s["confidence"] for s in terminal_members]
                    + [a["confidence"] for a in strong]
                ),
            }
        )

        decisions.append(
            {
                "group_id": g["group_id"],
                "status": "ACCEPTED",
                "reason": reason,
            }
        )

    # Cross-page merges require explicit tags and a unique occurrence per page.
    buckets = {}

    for e in accepted:
        key = (
            (e["doc"], e["equipment_type"], e["tag"])
            if e["tag"]
            else (e["equipment_id"],)
        )

        buckets.setdefault(key, []).append(e)

    merged = []

    for bucket in buckets.values():
        pages = [
            e["occurrences"][0]["page"]
            for e in bucket
        ]

        if len(pages) != len(set(pages)):
            for e in bucket:
                for decision in decisions:
                    if (
                        decision.get("group_id") + "_EQ"
                        == e["equipment_id"]
                    ):
                        decision.update(
                            status="UNRESOLVED",
                            reason="DUPLICATE_INSTANCE_TAG_ON_PAGE",
                        )
            continue

        e = dict(bucket[0])

        for field in (
            "source_symbol_ids",
            "occurrences",
            "anchor_ids",
        ):
            e[field] = [
                v
                for item in bucket
                for v in item[field]
            ]

        e["confidence"] = min(
            item["confidence"]
            for item in bucket
        )

        merged.append(e)

    return merged, decisions


def family_cardinality(pages, equipment):
    diagnostics = []

    for page in pages:
        for a in page.get("text_equipment_anchors", []):
            if a.get("anchor_role") != "CARDINALITY":
                continue

            count = (
                a.get("attributes", {})
                .get("declared_member_count")
            )

            members = [
                e["equipment_id"]
                for e in equipment
                if a["anchor_id"] in e["anchor_ids"]
            ]

            diagnostics.append(
                {
                    "anchor_id": a["anchor_id"],
                    "declared_count": count,
                    "explicitly_supported_member_ids": members,
                    "status": "UNRESOLVED_FAMILY_MEMBERSHIP",
                    "reason": (
                        "CARDINALITY_DOES_NOT_GENERATE_INSTANCES_"
                        "OR_ASSIGN_NEIGHBOURS"
                    ),
                }
            )

    return diagnostics