from .evidence_filtering import filter_evidence
from .equipment_consolidation import consolidate
from .central_inverter_rules import decide_equipment, family_cardinality
from .hierarchy import resolve_relations, build_hierarchy
from .validation import validate
from .candidate_feature_extraction import extract_candidate_features
from .resolution_engine import build_resolution_requests
from .container_resolution import resolve_conversion_units
from .operator_feedback_resolution import apply_operator_feedback
from .target_hierarchy import build_target_hierarchy
from .target_entity_resolution import resolve_target_entities
from .detail_page_resolution import resolve_detail_page_transformers


def interpret(
    pages, geometry=None, learned_patterns=None, operator_feedback=None,
    supplemental_container_entities=None, supplemental_target_entities=None,
):
    operator_feedback = list(operator_feedback or [])
    supplemental_container_entities = list(supplemental_container_entities or [])
    supplemental_target_entities = list(supplemental_target_entities or [])
    scope = filter_evidence(pages, geometry)
    groups = consolidate(pages, scope)
    equipment, decisions = decide_equipment(groups)
    feature_profiles = extract_candidate_features(pages, groups)

    container_resolution = resolve_conversion_units(
        pages, learned_patterns=learned_patterns, operator_feedback=operator_feedback,
        supplemental_entities=supplemental_container_entities,
    )

    equipment, operator_diagnostics = apply_operator_feedback(
        groups, equipment, operator_feedback
    )

    detail_page_resolution = resolve_detail_page_transformers(
        pages, accepted_equipment=equipment
    )

    target_entities = resolve_target_entities(
        pages, equipment,
        supplemental_entities=(
            list(detail_page_resolution.get("entities", []) or [])
            + supplemental_target_entities
        ),
    )
    equipment = target_entities['entities']

    relations, unresolved = resolve_relations(pages, equipment)
    hierarchy = build_hierarchy(equipment, relations)
    target_hierarchy = build_target_hierarchy(
        pages, container_resolution, equipment
    )

    resolution_requests = build_resolution_requests(
        pages, feature_profiles, equipment,
        container_resolution=container_resolution,
        operator_feedback=operator_feedback,
        target_hierarchy=target_hierarchy,
    )

    return {
        'scope_decisions': scope,
        'equipment_groups': [
            {
                'group_id': g['group_id'],
                'source_symbol_ids': [s['symbol_id'] for s in g['members']],
                'scope_status': g['scope_status'],
            } for g in groups
        ],
        'family_cardinality': family_cardinality(pages, equipment),
        'equipment_decisions': decisions,
        'candidate_feature_profiles': feature_profiles,
        'container_resolution': container_resolution,
        'detail_page_resolution': detail_page_resolution,
        'operator_feedback_diagnostics': operator_diagnostics,
        'target_entity_resolution': target_entities,
        'resolution_requests': resolution_requests,
        'accepted_equipment': equipment,
        'accepted_relations': relations,
        'unresolved_relations': unresolved,
        'hierarchy': hierarchy,
        'target_hierarchy': target_hierarchy,
        'validation': validate(pages, equipment, relations, hierarchy),
    }
