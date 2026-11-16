"""Consolidate physical evidence, preserving all original candidate IDs."""
from .evidence_filtering import hard_rejected


def overlap(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    aa = max(0, a[2]-a[0])*max(0, a[3]-a[1])
    bb = max(0, b[2]-b[0])*max(0, b[3]-b[1])
    return intersection / max(aa, bb, 1e-9)


def consolidate(pages, scope):
    groups = []
    all_anchors = {a['anchor_id']: a for page in pages for a in page.get('text_equipment_anchors', [])}
    for page in pages:
        symbols = [s for s in page.get('symbol_candidates', []) if not hard_rejected(s) and scope[s['symbol_id']]['status'] != 'OUT_OF_SCOPE']
        # Geometry first; text-only evidence may join only through the same anchor.
        symbols.sort(key=lambda s: (s['evidence_state'] == 'TEXT_ONLY', s['symbol_id']))
        for s in symbols:
            matches = []
            for g in groups:
                if g['doc'] != s['doc'] or g['page'] != s['page']:
                    continue
                for old in g['members']:
                    same_anchor = (s['evidence_state'] == 'TEXT_ONLY' or old['evidence_state'] == 'TEXT_ONLY') and s.get('text_anchor_id') and s.get('text_anchor_id') == old.get('text_anchor_id')
                    same_shape = (s['evidence_state'] != 'TEXT_ONLY' and old['evidence_state'] != 'TEXT_ONLY' and overlap(s['bbox'], old['bbox']) >= .85)
                    incompatible_tags = s.get('tag') and old.get('tag') and s['tag'].upper() != old['tag'].upper()
                    types = {s['candidate_type'], old['candidate_type']}
                    compatible = (len(types) == 1 or types <= {'CENTRAL_INVERTER', 'CENTRAL_INVERTER_CANDIDATE', 'ELECTRICAL_ENCLOSURE_CANDIDATE'} or types <= {'MV_LV_TRANSFORMER', 'PAIRED_CIRCLE_ELECTRICAL_CANDIDATE', 'TRANSFORMER_CANDIDATE'})
                    if (same_anchor or same_shape) and compatible and not incompatible_tags:
                        matches.append(g); break
            if len(matches) == 1:
                matches[0]['members'].append(s)
            else:
                groups.append({'group_id': s['symbol_id']+'_GROUP', 'doc': s['doc'], 'page': s['page'], 'members': [s]})
    for g in groups:
        g['anchors'] = []
        for s in g['members']:
            a = all_anchors.get(s.get('text_anchor_id'))
            if a and a not in g['anchors']:
                g['anchors'].append(a)
        g['scope_status'] = 'IN_SCOPE' if any(scope[s['symbol_id']]['status'] == 'IN_SCOPE' for s in g['members']) else 'UNRESOLVED'
    return groups
