"""Runtime invariants, independent from external benchmark ground truth."""
from .evidence_filtering import hard_rejected
from .hierarchy import ALLOWED


def validate(pages, equipment, relations, hierarchy):
    issues = []
    def issue(code, **context): issues.append({'severity': 'ERROR', 'code': code, **context})
    symbols = {s['symbol_id']: s for p in pages for s in p.get('symbol_candidates', [])}
    ids = [e['equipment_id'] for e in equipment]
    if len(ids) != len(set(ids)): issue('DUPLICATE_EQUIPMENT_ID')
    entities = {e['equipment_id']: e for e in equipment}
    used = set()
    for e in equipment:
        if not e.get('acceptance_reason') or not e.get('occurrences'): issue('MISSING_POSITIVE_EVIDENCE', equipment_id=e['equipment_id'])
        for sid in e['source_symbol_ids']:
            if sid not in symbols: issue('MISSING_SOURCE_SYMBOL', symbol_id=sid)
            elif hard_rejected(symbols[sid]): issue('REJECTED_SYMBOL_ACCEPTED', symbol_id=sid)
            if sid in used: issue('SOURCE_SYMBOL_ACCEPTED_TWICE', symbol_id=sid)
            used.add(sid)
    traces = {r['relation_id'] for p in pages for r in p.get('terminal_tracing', {}).get('relations', [])}
    for r in relations:
        if r['source_equipment_id'] not in entities or r['target_equipment_id'] not in entities: issue('ENDPOINT_NOT_ACCEPTED', relation_id=r['relation_id'])
        if not r['source_trace_ids'] or any(t not in traces for t in r['source_trace_ids']): issue('MISSING_TRACE_PROVENANCE', relation_id=r['relation_id'])
    parents = {n['equipment_id']: n['parent_id'] for n in hierarchy}
    for child, parent in parents.items():
        if parent:
            if parent not in entities or child not in entities: issue('MISSING_HIERARCHY_ENDPOINT')
            elif entities[child]['equipment_type'] not in ALLOWED.get(entities[parent]['equipment_type'], set()): issue('INVALID_PARENT_TYPE', child=child)
        visited = {child}; current = parent
        while current:
            if current in visited: issue('HIERARCHY_CYCLE', child=child); break
            visited.add(current); current = parents.get(current)
    failed = [p['page'] for p in pages if p.get('page_type') == 'ERROR']
    if failed: issue('PAGE_ANALYSIS_FAILED', pages=failed)
    return {'status': 'FAIL' if issues else 'PASS', 'issues': issues, 'ground_truth_used': False,
            'unresolved_hierarchy_nodes': sum(n['parent_id'] is None for n in hierarchy)}


def benchmark_tags(predicted, expected):
    """External-only utility; never invoked by inference. None for undefined rates."""
    p, g = set(predicted), set(expected)
    tp = len(p & g)
    return {'tp': tp, 'fp': len(p-g), 'fn': len(g-p),
            'precision': tp/len(p) if p else None, 'recall': tp/len(g) if g else None}
