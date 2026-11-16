"""Conservative, plant-local documentary cross-sheet connection evidence.

The references are NOT physical conductor paths or electrical feeder roots. An
edge needs independent opposite-side references from pages uniquely identified
by dev14c's SOURCE_INSTANCE provenance. No numbers, labels or expected group
sizes are hard-coded. No benchmark/ground_truth or learned foreign-plant input.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import re
import unicodedata

SCHEMA = 'sld-beta3-cross-sheet-reference/v1'
# Reference token (not a free text match). Expanded multilingual vocabulary is
# allowed only with an independently classified CROSS_SHEET_REFERENCE anchor.
TO = {'A', 'TO', 'PARA', 'HACIA', 'VERS', 'TOWARDS'}
FROM = {'DE', 'DA', 'DI', 'FROM', 'DESDE'}
PREFIX = re.compile(r'^([A-Za-zÀ-ÿ]+)\s+\S+', re.UNICODE)


def _norm(text):
    s = unicodedata.normalize('NFKD', str(text or ''))
    return ''.join(c for c in s if not unicodedata.combining(c)).upper().strip()


def _sortkey(key):
    return (0, int(key)) if str(key).isdigit() else (1, str(key))


def _direction(anchor):
    raw = _norm(anchor.get('text'))
    m = PREFIX.match(raw)
    if not m:
        return None
    prefix = m.group(1)
    if prefix in TO:
        return 'TO'
    if prefix in FROM:
        return 'FROM'
    return None


def _usable_bbox(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        numbers = list(map(float, value))
        return numbers if numbers[0] < numbers[2] and numbers[1] < numbers[3] else None
    except (TypeError, ValueError):
        return None


def analyze_cross_sheet(base: dict) -> dict:
    """Build two-sided documentary links and separate connectivity groups.

    Source CU must be unique *by identity* on a page. Same CU repeated on a
    page is permitted; multiple different CU identities are not. The target
    must be canonical for this plant, never inferred from a page ordinal.
    """
    reconciliation = base.get('source_reconciliation') or {}
    cu_rows = reconciliation.get('conversion_units') or []
    plant_id = (base.get('plant') or {}).get('plant_id')
    identities = {}
    page_owners = defaultdict(set)
    for cu in cu_rows:
        key = str(cu.get('instance_key'))
        cu_id = cu.get('canonical_cu_id')
        if not key or key == 'None' or not cu_id or key in identities:
            continue
        identities[key] = str(cu_id)
        for rep in cu.get('sld_representations') or []:
            if rep.get('representation_role') == 'SOURCE_INSTANCE':
                try:
                    page_owners[int(rep['page'])].add(key)
                except (ValueError, TypeError, KeyError):
                    pass
    findings = []
    refusals = []
    by_link = defaultdict(list)
    for page in base.get('pages') or []:
        if page.get('page_type') == 'ERROR':
            continue
        try:
            number = int(page['page'])
        except (ValueError, TypeError, KeyError):
            continue
        for anchor in page.get('text_equipment_anchors') or []:
            if anchor.get('anchor_role') != 'REFERENCE':
                continue
            if (anchor.get('attributes') or {}).get('representation_role') != 'CROSS_SHEET_REFERENCE':
                continue
            ref = {'page': number, 'anchor_id': anchor.get('anchor_id'),
                   'text': anchor.get('text'), 'bbox': _usable_bbox(anchor.get('bbox')),
                   'source': anchor.get('source'), 'tag': anchor.get('tag')}
            owners = page_owners.get(number, set())
            if len(owners) != 1:
                refusals.append({**ref, 'reason': 'AMBIGUOUS_OR_MISSING_SOURCE_CU_ON_PAGE',
                                 'source_cu_candidates': sorted(owners, key=_sortkey)})
                continue
            origin = next(iter(owners))
            attrs = anchor.get('attributes') or {}
            target_hint = attrs.get('instance_hint')
            target = str(target_hint) if target_hint is not None else ''
            if target not in identities:
                refusals.append({**ref, 'reason': 'TARGET_NOT_CANONICAL_IN_THIS_PLANT'})
                continue
            if target == origin:
                refusals.append({**ref, 'reason': 'SELF_REFERENCE_NOT_A_CU_LINK'})
                continue
            direction = _direction(anchor)
            if direction is None:
                refusals.append({**ref, 'reason': 'UNKNOWN_REFERENCE_DIRECTION'})
                continue
            # TO and FROM describe continuation labels, not power-flow arrows.
            side = 'ORIGIN_PAGE_TO' if direction == 'TO' else 'DESTINATION_PAGE_FROM'
            src, dst = (origin, target) if direction == 'TO' else (target, origin)
            by_link[(src, dst)].append({**ref, 'page_cu_key': origin,
                                         'reference_to_cu_key': target, 'reference_side': side})
    confirmed = []
    pending = []
    for (src, dst), evidences in sorted(by_link.items(), key=lambda x: (_sortkey(x[0][0]), _sortkey(x[0][1]))):
        sides = defaultdict(list)
        for ev in evidences:
            sides[ev['reference_side']].append(ev)
        valid = (len(sides['ORIGIN_PAGE_TO']) == 1 and
                 len(sides['DESTINATION_PAGE_FROM']) == 1 and
                 sides['ORIGIN_PAGE_TO'][0]['page'] != sides['DESTINATION_PAGE_FROM'][0]['page'])
        status = ('RECIPROCAL_DOCUMENTARY_REFERENCE' if valid else
                  'AMBIGUOUS_MULTIPLE_SIDE_REFERENCES' if any(len(v) > 1 for v in sides.values()) else
                  'ONE_SIDED_DOCUMENTARY_REFERENCE')
        link = {'from_cu_id': identities[src], 'to_cu_id': identities[dst],
                'from_instance_key': src, 'to_instance_key': dst,
                'status': status,
                'evidence': sorted(evidences, key=lambda r:(r['page'], str(r['anchor_id']))),
                'physical_terminal_verified': False,
                'electrical_path_verified': False,
                'flow_direction_verified': False}
        (confirmed if valid else pending).append(link)
    # Connected components from confirmed documentary links ONLY; no layout
    # group or expected number is consulted to construct components.
    adjacency = defaultdict(set)
    for link in confirmed:
        a, b = link['from_instance_key'], link['to_instance_key']
        adjacency[a].add(b)
        adjacency[b].add(a)
    groups, visited = [], set()
    for key in sorted(identities, key=_sortkey):
        if key in visited:
            continue
        nodes, frontier = [], [key]
        visited.add(key)
        while frontier:
            n = frontier.pop()
            nodes.append(n)
            for nb in sorted(adjacency[n], key=_sortkey):
                if nb not in visited:
                    visited.add(nb)
                    frontier.append(nb)
        nodes.sort(key=_sortkey)
        groups.append({'group_id': f'CROSS_SHEET_GROUP_{len(groups) + 1:03d}',
                       'cu_instance_keys': nodes,
                       'canonical_cu_ids': [identities[k] for k in nodes],
                       'evidence_level': 'RECIPROCAL_DOCUMENTARY_ONLY',
                       'electrical_feeder_verified': False})
    assignments = defaultdict(set)
    for a in reconciliation.get('cu_mv_membership') or []:
        key, feeder = a.get('cu_instance_key'), a.get('mv_line_instance_key')
        if key is not None and feeder is not None:
            assignments[str(key)].add(str(feeder))
    comparable = [link for link in confirmed if
                  len(assignments[link['from_instance_key']]) == 1 and
                  len(assignments[link['to_instance_key']]) == 1]
    disagree = [link for link in comparable if
                assignments[link['from_instance_key']] != assignments[link['to_instance_key']]]
    return {'schema': SCHEMA, 'plant_id': plant_id,
            'status': 'DOCUMENTARY_DIAGNOSTIC_ONLY',
            'reciprocal_links': confirmed, 'incomplete_links': pending,
            'refused_references': refusals,
            'connected_groups': groups,
            'independent_layout_comparison': {
                'comparable_links': len(comparable),
                'same_layout_feeder': len(comparable) - len(disagree),
                'conflicting_layout_feeder': len(disagree),
                'uncomparable_links': len(confirmed) - len(comparable),
                'conflicts': [{'from_cu_id': e['from_cu_id'], 'to_cu_id': e['to_cu_id']}
                              for e in disagree],
                'note': 'Post-hoc comparison only; layout is not used to create cross-sheet edges'},
            'summary': {
                'canonical_cus': len(identities),
                'reciprocal_documentary_links': len(confirmed),
                'one_sided_or_ambiguous_links': len(pending),
                'refused_references': len(refusals),
                'cross_sheet_groups': len(groups),
                'group_sizes': [len(g['cu_instance_keys']) for g in groups],
                'electrical_paths_verified': 0,
                'graph_verified_feeder_memberships': 0},
            'policy': ('Cross-sheet refs require two uniquely anchored opposed descriptions; '
                       'neither a reference nor a group proves through-device continuity, feeder root or flow')}
