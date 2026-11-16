"""Downstream scope decisions from electrically supported local regions.
No candidate is mutated or discarded; no automatic rectangular title-block crop.
"""

from .config import GeometryThresholds


def hard_rejected(symbol):
    return (symbol['candidate_type'].startswith('REJECTED_') or
            symbol.get('evidence', {}).get('scale_status') == 'OUTLIER')


def _contained(inner, outer):
    return inner[0]>=outer[0] and inner[1]>=outer[1] and inner[2]<=outer[2] and inner[3]<=outer[3]


def filter_evidence(pages, geometry=None):
    threshold = geometry or GeometryThresholds()
    decisions = {}
    for page in pages:
        anchors = {a['anchor_id']: a for a in page.get('text_equipment_anchors', [])}
        # Region identity is source provenance, not a heuristic page crop.
        regions = []
        for s in page.get('symbol_candidates', []):
            if hard_rejected(s): continue
            if (s.get('terminals') and s.get('text_anchor_id') in anchors) or s.get('evidence',{}).get('scale_status')=='REFERENCE':
                regions.append((s['symbol_id'],s['bbox']))
        for s in page.get('symbol_candidates', []):
            a = anchors.get(s.get('text_anchor_id'))
            memberships = [rid for rid,bbox in regions if _contained(s['bbox'],bbox)]
            refs = page.get('symbol_scale_coherence', {}).get('references', [])
            scale_conflict = False
            if s['candidate_type'] == 'CENTRAL_INVERTER' and s['evidence_state'] != 'TEXT_ONLY' and refs:
                cx,cy = (s['bbox'][0]+s['bbox'][2])/2,(s['bbox'][1]+s['bbox'][3])/2
                ref = min(refs,key=lambda r:(cx-r['center'][0])**2+(cy-r['center'][1])**2)
                dims = sorted([s['bbox'][2]-s['bbox'][0],s['bbox'][3]-s['bbox'][1]])
                ratios = [dims[0]/max(ref['short_side_pt'],1e-9),dims[1]/max(ref['long_side_pt'],1e-9)]
                scale_conflict = any(not threshold.ci_scale_consistent_ratio_min <= v <= threshold.ci_scale_consistent_ratio_max for v in ratios)
            if hard_rejected(s):
                state, reason = 'OUT_OF_SCOPE', 'HARD_REJECTED'
            elif scale_conflict:
                state, reason = 'OUT_OF_SCOPE', 'DOWNSTREAM_LOCAL_CI_SCALE_CONFLICT'
            elif s.get('terminals') and a:
                state, reason = 'IN_SCOPE', 'SOURCE_TEXT_AND_GRAPH_TERMINALS'
            elif s.get('geometry_kind') == 'TEXT_GUIDED_VECTOR_ENCLOSURE':
                state, reason = 'IN_SCOPE', 'LOCAL_TEXT_GUIDED_REGION_REFERENCE'
            elif memberships and s.get('terminals'):
                state, reason = 'IN_SCOPE', 'TERMINAL_SYMBOL_IN_SOURCE_SUPPORTED_REGION'
            else:
                state, reason = 'UNRESOLVED', 'INSUFFICIENT_ELECTRICAL_REGION_EVIDENCE'
            decisions[s['symbol_id']] = {'status': state, 'reason': reason, 'source_region_ids': memberships}
    return decisions
