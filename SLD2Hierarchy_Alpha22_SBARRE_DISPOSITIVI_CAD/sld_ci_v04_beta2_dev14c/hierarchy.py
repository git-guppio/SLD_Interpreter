"""Electrical connectivity and asset containment are separate semantics.
Upstream/downstream is an asset orientation, never an assertion of power flow.
"""
ALLOWED = {'CONVERSION_UNIT': {'MV_LV_TRANSFORMER'},
           'MV_LV_TRANSFORMER': {'CENTRAL_INVERTER'},
           'CENTRAL_INVERTER': {'STRING_BOX'}}


def resolve_relations(pages, equipment):
    by_symbol = {sid: e for e in equipment for sid in e['source_symbol_ids']}
    accepted, unresolved = [], []
    seen = set()
    for page in pages:
        for r in page.get('terminal_tracing', {}).get('relations', []):
            a, b = by_symbol.get(r['source_symbol_id']), by_symbol.get(r['target_symbol_id'])
            if not a or not b:
                unresolved.append({'source_relation_id': r['relation_id'], 'reason': 'ENDPOINT_NOT_ACCEPTED'}); continue
            if a['equipment_id'] == b['equipment_id']:
                continue
            key = tuple(sorted([a['equipment_id'], b['equipment_id']]))
            if key in seen:
                continue
            seen.add(key)
            # A conductor path proves connectivity, not enclosure containment.
            accepted.append({'relation_id': r['relation_id']+'_ACCEPTED', 'relation_type': 'CONNECTED_TO',
                             'source_equipment_id': a['equipment_id'], 'target_equipment_id': b['equipment_id'],
                             'source_trace_ids': [r['relation_id']], 'confidence': min(a['confidence'], b['confidence'], r['confidence']),
                             'direction_status': 'UNDIRECTED'})
    return accepted, unresolved


def build_hierarchy(equipment, relations):
    entities = {e['equipment_id']: e for e in equipment}
    options = {eid: set() for eid in entities}
    for r in relations:
        a, b = entities[r['source_equipment_id']], entities[r['target_equipment_id']]
        for parent, child in ((a,b),(b,a)):
            # CU containment requires independent enclosure evidence; no such inference from wires.
            if parent['equipment_type'] == 'CONVERSION_UNIT':
                continue
            if child['equipment_type'] in ALLOWED.get(parent['equipment_type'], set()):
                options[child['equipment_id']].add(parent['equipment_id'])
    return [{'equipment_id': eid, 'parent_id': next(iter(parents)) if len(parents)==1 else None,
             'status': 'RESOLVED' if len(parents)==1 else 'UNRESOLVED_MULTIPLE_PARENTS' if parents else 'UNRESOLVED_NO_PARENT',
             'parent_candidates': sorted(parents), 'basis': 'ASSET_DOMAIN_ORDER_AND_TRACED_CONNECTIVITY' if len(parents)==1 else None}
            for eid, parents in options.items()]
