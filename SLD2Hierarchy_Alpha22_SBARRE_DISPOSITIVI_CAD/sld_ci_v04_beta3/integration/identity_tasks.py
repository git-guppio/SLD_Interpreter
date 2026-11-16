"""Evidence-first *verification work queue* based on independently inferred CU identities.

No precondition that two FUSED symbols share a page; no text-to-terminal
promotion. Membership from layout is an assignment hypothesis, not an
SLD electric root or a graph-verified path. This module never reads GT.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from math import hypot
from pathlib import Path

from ..geometry.kernel import extract_pdf, build_graph
from ..geometry.roi import clip_to_roi
from ..geometry.classify import classify_strokes


def _bbox(box):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x0,y0,x1,y1 = map(float,box)
        if x0 < x1 and y0 < y1:
            return [x0,y0,x1,y1]
    except (TypeError,ValueError):
        pass
    return None


def _page_index(pages):
    return {int(p['page']):p for p in pages if p.get('page') is not None and p.get('page_type')!='ERROR'}


def plan_cu_verifications(base:dict) -> dict:
    """One auditable task per canonical CU, not one task per ambiguous label.

    Task generation is deterministic and generic. Terminal evidence can only be
    used when dev14c references the *same text anchor* and reports a terminal.
    Layout membership is never treated as a feeder's SLD graph root.
    """
    rec=base.get('source_reconciliation') or {}
    pages=_page_index(base.get('pages') or [])
    memberships=defaultdict(list)
    for m in rec.get('cu_mv_membership') or []:
        memberships[str(m.get('cu_instance_key'))].append(m)
    out=[]
    for cu in rec.get('conversion_units') or []:
        key=str(cu.get('instance_key'))
        c_id=cu.get('canonical_cu_id')
        ms=memberships.get(key,[])
        m=ms[0] if len(ms)==1 else None
        witnesses=[]
        terminal_evidence=[]
        feeder_labels=[]
        missing=Counter()
        for rep in cu.get('sld_representations') or []:
            try:pg=int(rep.get('page'))
            except (TypeError,ValueError):missing['INVALID_PAGE']+=1;continue
            page=pages.get(pg)
            if page is None:
                missing['SLD_PAGE_NOT_AVAILABLE']+=1;continue
            aid=rep.get('anchor_id')
            anchors=[x for x in page.get('text_equipment_anchors') or []
                     if aid and x.get('anchor_id')==aid]
            if len(anchors)!=1:
                missing['NO_UNIQUE_SOURCE_ANCHOR']+=1;continue
            anchor=anchors[0]
            # These may be documentary MV labels, not conductive graph roots.
            for mv in page.get('mv_line_anchors') or []:
                feeder_labels.append({'page':pg,'label':mv.get('tag') or mv.get('text'),
                   'anchor_id':mv.get('anchor_id'),
                   'bbox':_bbox(mv.get('bbox')),
                   'root_status':'NOT_GEOMETRICALLY_VERIFIED'})
            box=_bbox(anchor.get('bbox'))
            if box is None:
                missing['MISSING_ANCHOR_BBOX']+=1;continue
            fused=[s for s in page.get('symbol_candidates') or []
                   if s.get('text_anchor_id')==aid and s.get('evidence_state')=='FUSED'
                   and s.get('terminals') and _bbox(s.get('bbox'))]
            row={'page':pg,'anchor_id':aid,'tag':anchor.get('tag'),
                 'bbox':box,'source_evidence':anchor.get('source'),
                 'representation_role':rep.get('representation_role'),
                 'physical_terminal_status':'FUSED_CANDIDATE_NOT_VERIFIED' if fused else 'UNBOUND'}
            witnesses.append(row)
            for s in fused:
                terminal_evidence.append({'page':pg,'symbol_id':s.get('symbol_id'),
                       'source_anchor_id':aid,'candidate_type':s.get('candidate_type'),
                       'bbox':list(s['bbox']), 'terminal_count':len(s['terminals']),
                       'geometry_kind':s.get('geometry_kind'),
                       'electrical_role_verified':False})
        # Original source order is preserved for audit. No arbitrary choice among
        # repeated labels, no new assignment based on mere nearest distance.
        if not witnesses:
            blocker='NO_SLD_CU_ANCHOR_WITH_COORDINATES'
        elif not terminal_evidence:
            blocker='NO_TERMINAL_BOUND_TO_CANONICAL_CU_ANCHOR'
        else:
            blocker='NEEDS_INDEPENDENT_SLD_FEEDER_ROOT_AND_DEVICE_TOPOLOGY'
        out.append({'canonical_cu_id':c_id,'cu_instance_key':key,
                    'layout_feeder_assignment':{
                       'status':('UNIQUE_INFERRED_ASSIGNMENT' if m and m.get('source_status')=='INFERRED'
                                 else 'UNIQUE_REPORTED_ASSIGNMENT' if m else 'UNRESOLVED'),
                       'line_key':m.get('mv_line_instance_key') if m else None,
                       'source_status':m.get('source_status') if m else None,
                       'basis':m.get('basis') if m else None,
                       'page':m.get('page') if m else None,
                       'evidence_anchor_id':m.get('cu_anchor_id') if m else None,
                       'graph_verified':False},
                    'sld_witnesses':witnesses,
                    'candidate_bound_terminals':terminal_evidence,
                    'sld_feeder_label_candidates':list({(x['page'],x['anchor_id']):x
                               for x in feeder_labels}.values()),
                    'blocker':blocker,'diagnostics':dict(missing),
                    'status':'PENDING_ELECTRICAL_VERIFICATION',
                    'graph_verified_feeder_membership':False})
    blockers=Counter(t['blocker'] for t in out)
    return {'schema':'sld-beta3-cu-verification-queue/v1',
            'tasks':out,'summary':{'canonical_cu_tasks':len(out),
                 'with_sld_anchor':sum(bool(t['sld_witnesses']) for t in out),
                 'with_same_anchor_terminal_candidate':sum(bool(t['candidate_bound_terminals']) for t in out),
                 'blockers':dict(blockers),
                 'graph_verified_feeder_membership':0},
            'policy':'Canonical identity provenance from dev14c; no electrical relation inferred from tag/layout alone'}


def inspect_identity_neighborhoods(sld_path, queue:dict, *, max_inspections=3,
                                   padding=50, max_strokes=1200):
    """Run geometry even if no two FUSED named symbols exist on the same page.

    Selects distinct CU identities and their source-anchored regions; outputs
    only diagnostic geometry, never a path/feeder claim. ROI edges are artificial.
    """
    import pymupdf
    if max_inspections < 0 or max_strokes < 1 or padding <= 0:
        raise ValueError('invalid neighborhood budget')
    choices=[]
    for task in queue['tasks']:
        witnesses=task.get('sld_witnesses') or []
        bound_ids={s.get('source_anchor_id') for s in task.get('candidate_bound_terminals') or []}
        # Prefer genuine same-anchor terminal evidence when present, then
        # source-instance witness order. Do not pretend the terminal is verified.
        witnesses=sorted(witnesses,key=lambda r:(r['anchor_id'] not in bound_ids,
                          r.get('representation_role')!='SOURCE_INSTANCE',r['page'],r['anchor_id']))
        if witnesses:
            choices.append((not bool(task['candidate_bound_terminals']),len(choices),task['canonical_cu_id'],witnesses[0]))
    choices.sort(key=lambda x:(x[0],x[1]))
    if not choices or max_inspections == 0:
        return []
    results=[]
    with pymupdf.open(str(sld_path)) as doc:
        for _,__,cu_id,w in choices[:max_inspections]:
            pg=w['page']; b=w['bbox']; page=doc[pg-1]
            r=page.cropbox
            roi=(max(r.x0,b[0]-padding),max(r.y0,b[1]-padding),
                 min(r.x1,b[2]+padding),min(r.y1,b[3]+padding))
            if roi[0]>=roi[2] or roi[1]>=roi[3]:
                results.append({'canonical_cu_id':cu_id,'page':pg,'status':'INVALID_ROI'});continue
            strokes,ignored,dots=extract_pdf(page,page_number=pg)
            clipped,clip_stats=clip_to_roi(strokes,roi)
            selected,class_stats=classify_strokes(clipped)
            dots=[q for q in dots if roi[0]<=q[0]<=roi[2] and roi[1]<=q[1]<=roi[3]]
            graph=build_graph(selected,dots=dots,max_strokes=max_strokes)
            results.append({'canonical_cu_id':cu_id,'page':pg,
                'source_anchor_id':w['anchor_id'],'roi':list(roi),
                'status':('INCOMPLETE' if graph['status']!='COMPLETE'
                          else 'NO_LOCAL_GRAPH_EVIDENCE' if graph['node_count']==0
                          else 'COMPLETE_DIAGNOSTIC'),
                'geometry':{'raw_strokes':len(strokes),'clipped_strokes':len(clipped),
                      'classified_candidates':len(selected),'graph_status':graph['status'],
                      'nodes':graph['node_count'],'edges':graph['edge_count'],
                      'components':graph.get('component_count'),
                      'clip_statistics':clip_stats['counts'],
                      'normalization':class_stats['counts'],
                      'warnings':graph.get('warnings',[])},
                'electrical_path_verified':False,
                'reason':'Single-CU anchor neighborhood; no independently verified feeder root/terminal pair'})
    return results
