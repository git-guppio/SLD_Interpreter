"""Electrical-symbol-guided *geometric* pair tracing on actual PDF pages.

The source of target symbols/terminal candidates is dev14c's current document
analysis, NEVER Ground Truth or benchmark counts. The result is diagnostic and
must not be inserted into verified feeder membership.

A cropped ROI cannot prove end-to-end connectivity and its boundary truncation
is explicitly recorded. No invented conductive bridge through a device body.
"""
from __future__ import annotations
from itertools import combinations
from math import dist
from pathlib import Path

import pymupdf

from ..geometry.kernel import extract_pdf, build_graph
from ..geometry.classify import classify_strokes
from ..geometry.roi import clip_to_roi
from .semantic_bridge import _external_adjacency, _nearest_node, _bfs

SCHEMA='sld-beta3-automatic-pair-trace/v1'


def eligible_symbols(page: dict) -> list[dict]:
    """Named text+geometry symbols only; never promote a TEXT_ONLY candidate."""
    return sorted((s for s in page.get('symbol_candidates', [])
                   if s.get('evidence_state') == 'FUSED' and s.get('tag')
                   and s.get('terminals') and len(s.get('bbox', [])) == 4),
                  key=lambda s: (str(s['symbol_id']), str(s['tag'])))


def plan_pairs(page: dict, *, max_pairs: int = 3, width: float | None = None,
               height: float | None = None) -> list[tuple[dict, dict]]:
    """Propose geographically proximal pairs, never an electrical relation.

    The relative span is a workload budget, not an electrical cutoff. No pair
    means 'not evaluated', not 'disconnected'.
    """
    if max_pairs < 0:
        raise ValueError('max_pairs must be nonnegative')
    syms=eligible_symbols(page)
    w=float(width or page.get('page_width_pt') or 1)
    h=float(height or page.get('page_height_pt') or 1)
    limit=0.27 * max(w,h)
    pairs=[]
    for a,b in combinations(syms, 2):
        if str(a.get('symbol_id')) == str(b.get('symbol_id')):
            continue
        ca=((a['bbox'][0]+a['bbox'][2])/2,(a['bbox'][1]+a['bbox'][3])/2)
        cb=((b['bbox'][0]+b['bbox'][2])/2,(b['bbox'][1]+b['bbox'][3])/2)
        d=dist(ca,cb)
        if d <= limit:
            pairs.append((d, str(a['symbol_id']), str(b['symbol_id']),a,b))
    pairs.sort(key=lambda pair: pair[:3])
    return [(x[3],x[4]) for x in pairs[:max_pairs]]


def _clip_pair_roi(a:dict,b:dict,page:pymupdf.Page,padding:float)->tuple[float,float,float,float]:
    x0=min(a['bbox'][0],b['bbox'][0]);y0=min(a['bbox'][1],b['bbox'][1])
    x1=max(a['bbox'][2],b['bbox'][2]);y1=max(a['bbox'][3],b['bbox'][3])
    r=page.cropbox
    return (max(r.x0,x0-padding),max(r.y0,y0-padding),
            min(r.x1,x1+padding),min(r.y1,y1+padding))


def pair_path(graph:dict,a:dict,b:dict, *, tolerance=0.75, roi=None) -> dict:
    """Only a candidate between two source-extracted terminal sets.

    Uses external graph, blocks entry through *both* device bodies, refuses
    ambiguous terminal snapping, preserves source segment IDs in found paths.
    """
    if graph.get('status') != 'COMPLETE':
        return {'status':'UNRESOLVED','reason':'GRAPH_INCOMPLETE'}
    if a.get('symbol_id') == b.get('symbol_id'):
        return {'status':'UNRESOLVED','reason':'SAME_DEVICE'}
    boxes=[tuple(a['bbox']),tuple(b['bbox'])]
    adj,blocked=_external_adjacency(graph,boxes,margin=max(0.35,tolerance/2))
    origins=[];targets=[]; ambiguities=0
    for symbol,into in ((a,origins),(b,targets)):
        for terminal in symbol.get('terminals',[]):
            node,err=_nearest_node(tuple(terminal['point']),adj,tolerance)
            if err:
                ambiguities+=1
            elif node not in into:
                into.append(node)
    if not origins or not targets:
        # Distances diagnose extraction/snapping failures; they do not invent a
        # terminal-to-conductor bridge. Keep evidence for the next iteration.
        def diagnostic(s):
            points=[tuple(t['point']) for t in s.get('terminals',[])]
            nodes=list(adj)
            return [{'point':list(p),'nearest_external_graph_node_distance_pt':
                     round(min((dist(p,n) for n in nodes),default=float('inf')),3)
                     if nodes else None} for p in points]
        return {'status':'UNRESOLVED','reason':'NO_UNAMBIGUOUS_TERMINAL_GRAPH_NODE',
                'unbound_or_ambiguous_terminals':ambiguities,
                'terminal_diagnostics_a':diagnostic(a),
                'terminal_diagnostics_b':diagnostic(b),
                'blocked_edges_through_devices':len(blocked)}
    options=[]
    for origin in origins:
        p=_bfs(adj,origin,set(targets))
        if p:
            options.append(p)
    if not options:
        return {'status':'DISCONNECTED_IN_ROI','reason':'NO_LOCAL_PATH',
                'blocked_edges_through_devices':len(blocked),
                'unbound_or_ambiguous_terminals':ambiguities}
    options.sort(key=lambda p:(len(p['source_stroke_ids']),p['nodes']))
    best=options[0]
    # Two unrelated paths could appear to join at an artificial clipping
    # boundary. Never count those as candidate internal continuity.
    if roi is not None:
        x0,y0,x1,y1=roi
        if any(abs(p[0]-x0)<=0.36 or abs(p[0]-x1)<=0.36 or
               abs(p[1]-y0)<=0.36 or abs(p[1]-y1)<=0.36
               for p in best['nodes']):
            return {'status':'UNRESOLVED',
                    'reason':'PATH_TOUCHES_ARTIFICIAL_ROI_BOUNDARY',
                    'path_evidence':best,
                    'blocked_edges_through_devices':len(blocked),
                    'verified_electrical':False,
                    'verified_feeder_membership':False}
    return {'status':'LOCAL_GEOMETRIC_PATH_CANDIDATE','path':best,
            'blocked_edges_through_devices':len(blocked),
            'unbound_or_ambiguous_terminals':ambiguities,
            'verified_electrical':False,'verified_feeder_membership':False}


def inspect_pair(pdf_path: str|Path, page_number:int,a:dict,b:dict, *,
                 padding:float=45, max_strokes:int=1200) -> dict:
    if padding<=0 or max_strokes<=0:raise ValueError('invalid budget')
    p=Path(pdf_path)
    with pymupdf.open(p) as doc:
        if page_number<1 or page_number>len(doc):raise ValueError('page invalid')
        page=doc[page_number-1]
        roi=_clip_pair_roi(a,b,page,padding)
        strokes,ignored,dots=extract_pdf(page,page_number=page_number)
        clipped,clip_stats=clip_to_roi(strokes,roi)
        selected,classification=classify_strokes(clipped)
        dots=[pt for pt in dots if roi[0]<=pt[0]<=roi[2] and roi[1]<=pt[1]<=roi[3]]
        graph=build_graph(selected,dots=dots,max_strokes=max_strokes)
    route=pair_path(graph,a,b,roi=roi)
    return {
        'schema':SCHEMA,'source_file':p.name,'page':page_number,
        'symbol_a':{'id':a['symbol_id'],'tag':a['tag'],'type':a.get('candidate_type')},
        'symbol_b':{'id':b['symbol_id'],'tag':b['tag'],'type':b.get('candidate_type')},
        'roi':list(roi),'scope':'ROI_ONLY',
        'geometry':{'status':graph['status'],'raw_strokes':len(strokes),
                    'retained_candidates':len(selected),'nodes':graph['node_count'],
                    'edges':graph['edge_count'],'normalization':classification['counts'],
                    'roi_clipping':clip_stats,
                    'warnings':graph.get('warnings',[])},
        'trace':route,'electrical_claim':'NOT_VERIFIED',
        'feeder_membership_claim':'NOT_VERIFIED',
        'ground_truth_used':False,'expected_counts_used':False,
        'notes':['Only geometric proximity selected this pair',
                 'ROI border cuts are artificial, not electrical endpoints',
                 'A candidate path does not prove device or feeder electrical connectivity'],
    }
