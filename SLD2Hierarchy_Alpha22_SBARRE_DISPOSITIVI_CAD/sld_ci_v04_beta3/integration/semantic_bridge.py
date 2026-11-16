"""Read-only bridge: dev14c's TEXT/SYMBOL evidence + beta3 vector support graph.

IMPORTANT: Even a found route is merely a *local geometric candidate*. It does not
verify feeder membership, current flow, equipment role, or a plant hierarchy.
No benchmark, ground-truth, or plant-specific constants are read here.

Safety contract:
 - Graph over cap => no symbol/terminal route, still report native semantic evidence.
 - TEXT_ONLY does not become an electrical device instance by proximity alone.
 - A device body blocks traversal; it is never implicitly a conductive wire.
 - Ambiguous associations do not get auto-accepted.
 - An ROI always means a diagnostic local scope, never page-wide completeness.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
from math import dist
from pathlib import Path
from typing import Any

import pymupdf

from ..geometry.kernel import extract_pdf, build_graph
from ..geometry.classify import classify_strokes
from sld_ci_v04_beta2_dev14c.config import GeometryThresholds
from sld_ci_v04_beta2_dev14c.ingestion import native_text_items
from sld_ci_v04_beta2_dev14c.text_detection import detect_text_equipment_anchors
from sld_ci_v04_beta2_dev14c.models import GraphNode
from sld_ci_v04_beta2_dev14c.symbol_detection import (
    detect_vector_symbol_candidates, fuse_text_and_vector_candidates,
)

SCHEMA = 'sld-beta3-semantic-bridge/v1'


def _in_roi(box, roi):
    if roi is None:
        return True
    x0, y0, x1, y1 = box
    a,b,c,d = roi
    # All four corners inside: avoid false boundary-terminal claims.
    return a <= x0 and c >= x1 and b <= y0 and d >= y1


def _nodes_from_graph(graph):
    degrees=defaultdict(int)
    for e in graph.get('edges', []):
        degrees[tuple(e['from'])]+=1
        degrees[tuple(e['to'])]+=1
    return [GraphNode(node_id=i,point=pt,node_type='BETA3_ENDPOINT_OR_JUNCTION',
                      degree=degree)
            for i,(pt,degree) in enumerate(sorted(degrees.items()), start=1)]


def _point_in_open_box(p, box, margin=0.12):
    return box[0]+margin < p[0] < box[2]-margin and box[1]+margin < p[1] < box[3]-margin


def _enters_body(a, b, box, margin=0.12):
    """Does the segment pass through the *open interior* of a symbol rectangle?

    Liang-Barsky clipping against an inset box. No accidental pass-through when
    a single edge crosses the entire symbol without internal graph vertices.
    """
    x0,y0,x1,y1=box
    x0+=margin; y0+=margin; x1-=margin; y1-=margin
    if x0>=x1 or y0>=y1:
        return False
    dx=b[0]-a[0];dy=b[1]-a[1]
    t0,t1=0.,1.
    for p,q in ((-dx,a[0]-x0),(dx,x1-a[0]),(-dy,a[1]-y0),(dy,y1-a[1])):
        if abs(p)<1e-12:
            if q < 0: return False
        else:
            r=q/p
            if p<0:
                t0=max(t0,r)
            else:
                t1=min(t1,r)
            if t0>t1:return False
    return t1>t0+1e-8


def _external_adjacency(graph, symbol_boxes, *, margin=0.12):
    adj=defaultdict(list);blocked=[]
    for e in graph.get('edges', []):
        a=tuple(e['from']);b=tuple(e['to'])
        if any(_enters_body(a,b,box,margin=margin) for box in symbol_boxes):
            blocked.append(e['source_sid']); continue
        adj[a].append((b,e['source_sid']))
        adj[b].append((a,e['source_sid']))
    return adj,blocked


def _nearest_node(point, adj, tolerance):
    result=[(dist(point,n),n) for n in adj if dist(point,n)<=tolerance]
    if not result: return None,'ANCHOR_NOT_ON_GRAPH'
    result.sort(key=lambda x: x[0]);p=result[0]
    if len(result)>1 and abs(result[1][0]-p[0])<=1e-6:
        return None,'AMBIGUOUS_FEEDER_ANCHOR'
    return p[1],None


def _bfs(adj, origin, targets):
    todo=deque([origin]); pred={origin:None};sid={}
    while todo:
        n=todo.popleft()
        if n in targets:
            path=[];sources=[];cur=n
            while cur is not None:
                path.append(list(cur))
                if pred[cur] is not None: sources.append(sid[cur])
                cur=pred[cur]
            path.reverse();sources.reverse()
            return {'nodes':path,'source_stroke_ids':sources,'terminal_point':list(n)}
        for dest,s in adj.get(n,[]):
            if dest not in pred:
                pred[dest]=n;sid[dest]=s;todo.append(dest)
    return None


def choose_unique_tag_roi(pdf_path: str | Path, page_number: int, tag: str, *, padding: float=70.0):
    """Deterministically frame one unique *detected text* label; no geometry claim.

    Refuses ambiguous repeated labels (common on multi-panel documents) rather
    than guessing which physical instance corresponds to an identity.
    """
    if padding <= 0: raise ValueError('padding must be > 0')
    p=Path(pdf_path)
    with pymupdf.open(p) as doc:
        if not 1<=page_number<=len(doc):raise ValueError('page outside PDF')
        page=doc[page_number-1]
        items,_=native_text_items(page,page_number,p.stem)
        matches=[a for a in detect_text_equipment_anchors(items)
                 if a.tag is not None and a.tag.upper()==tag.upper()
                 and a.anchor_role in ('INSTANCE','TAG')]
        if len(matches)!=1:
            raise ValueError(f'Expected one unique instance/tag {tag!r}; found {len(matches)}')
        x0,y0,x1,y1=matches[0].bbox
        rect=page.cropbox  # unrotated page coordinates, as get_text/get_drawings
        roi=(max(rect.x0,x0-padding),max(rect.y0,y0-padding),
             min(rect.x1,x1+padding),min(rect.y1,y1+padding))
        return roi, {'anchor_id':matches[0].anchor_id,'tag':matches[0].tag,
                     'bbox':list(matches[0].bbox),'selector':'UNIQUE_SOURCE_TEXT_TAG',
                     'roi_padding_pt':padding}

def inspect_page(pdf_path: str | Path, page_number: int=1, *, roi=None,
                 max_strokes: int=1200, feeder_point=None, feeder_label=None,
                 plant_id=None, target_tag=None):
    """Independent semantic/geometry audit; never updates any CASE or legacy DB.

    A feeder point supplied by the operator is the *only* feeder graph root
    accepted here. A label alone is not a topology anchor. Plant ID is required
    when supplied with a feeder label to avoid leaking between plants.
    """
    if max_strokes<1:raise ValueError('max_strokes must be positive')
    if (feeder_label is not None or feeder_point is not None) and not plant_id:
        raise ValueError('plant_id is mandatory for any operator feeder information')
    if feeder_label is not None and feeder_point is None:
        raise ValueError('feeder_label needs an explicit coordinate feeder_point')
    if roi is not None and not (len(roi)==4 and roi[0]<roi[2] and roi[1]<roi[3]):
        raise ValueError('ROI invalid')
    if feeder_point is not None and len(feeder_point)!=2:
        raise ValueError('feeder_point requires x, y')
    p=Path(pdf_path)
    if not p.is_file():raise FileNotFoundError(p)
    with pymupdf.open(p) as doc:
        if not 1<=page_number<=len(doc):raise ValueError('page outside PDF')
        page=doc[page_number-1]
        text_items,text_stats=native_text_items(page,page_number,p.stem)
        anchors=detect_text_equipment_anchors(text_items)
        anchors=[a for a in anchors if _in_roi(a.bbox,roi)]
        # No anchor is promoted into a physical instance by text alone.
        semantic=[{'id':a.anchor_id,'type':a.equipment_type,'role':a.anchor_role,
                   'tag':a.tag,'text':a.text[:160],'bbox':list(a.bbox),
                   'source':a.source,'evidence_kind':a.evidence_kind,
                   'confidence':a.confidence,'connection_status':'TEXT_ONLY'} for a in anchors]

        strokes,ignored,dots=extract_pdf(page,page_number=page_number)
        selected,classification=classify_strokes(strokes,roi=roi)
        if roi is not None:
            x0,y0,x1,y1=roi
            dots=[v for v in dots if x0<=v[0]<=x1 and y0<=v[1]<=y1]
        graph=build_graph(selected,dots=dots,max_strokes=max_strokes)
        result={
          'schema':SCHEMA,'pdf_name':p.name,'page':page_number,
          'page_count':len(doc),'scope':'ROI_ONLY' if roi is not None else 'FULL_PAGE',
          'roi':list(roi) if roi is not None else None,
          'text':{'statistics':text_stats,'semantic_anchors':semantic,'anchor_count':len(anchors)},
          'geometry':{'status':graph['status'],'raw_strokes':len(strokes),
                      'retained_candidates':len(selected),'normalization':classification['counts'],
                      'graph_nodes':graph['node_count'],'graph_edges':graph['edge_count'],
                      'graph_components':graph['component_count'],
                      'junction_dot_candidates':len(dots),'ignored_items':len(ignored),
                      'warnings':graph.get('warnings',[])},
          'symbols':[], 'traces':[], 'feeder_documental_membership':[],
          'feeder_graph_verified_membership':[],
          'ground_truth_used':False,'expected_counts_used':False,
          'dev14c_modified':False,'case_output_modified':False,
          'notes':[],
        }
        if graph['status']!='COMPLETE':
            result['status']='INCOMPLETE';result['notes'].append('GEOMETRY_SAFETY_CAP: semantic evidence only')
            return result

        config=GeometryThresholds()
        nodes=_nodes_from_graph(graph)
        candidates=detect_vector_symbol_candidates(page,page_number,p.stem,nodes,config)
        if roi is not None:
            candidates=[c for c in candidates if _in_roi(c.bbox,roi)]
        fused=fuse_text_and_vector_candidates(candidates,anchors,float(page.rect.width),float(page.rect.height),config)
        symbols=[]
        for s in fused:
            if s.evidence_state=='TEXT_ONLY': continue # already present in semantic anchors
            symbols.append({'symbol_id':s.symbol_id,'candidate_type':s.candidate_type,
                            'bbox':list(s.bbox),'evidence_state':s.evidence_state,
                            'tag':s.tag,'text_anchor_id':s.text_anchor_id,
                            'geometry_kind':s.geometry_kind,
                            'terminals':[{'point':list(t.point),'graph_node_id':t.graph_node_id,
                                          'terminal_id':t.terminal_id,'side':t.side}
                                         for t in s.terminals],
                            'status':'CANDIDATE_NOT_ACCEPTED_AS_ASSET',
                            'source':'DEV14C_VECTOR_SYMBOL_DETECTOR_AND_TEXT_FUSION'})
        result['symbols']=symbols
        # Only explicitly fused text+geometry may be considered named equipment
        # endpoints. Geometry-only candidates stay as anonymous blockers.
        fused_named=[s for s in fused if s.evidence_state=='FUSED' and s.terminals and
                     s.tag is not None and (target_tag is None or s.tag.upper()==target_tag.upper())]
        if feeder_point is not None:
            boxes=[s.bbox for s in fused if s.evidence_state!='TEXT_ONLY' and s.terminals]
            adj,blocked=_external_adjacency(graph,boxes)
            result['geometry']['blocked_edges_through_symbols']=len(blocked)
            start,err=_nearest_node(tuple(float(x) for x in feeder_point),adj,0.75)
            if err:
                result['traces'].append({'status':'UNRESOLVED','reason':err,
                                         'provenance':'OPERATOR_PROVIDED',
                                         'operator_plant_id':plant_id,'feeder_label':feeder_label})
            elif not fused_named:
                result['traces'].append({'status':'UNRESOLVED','reason':'NO_NAMED_FUSED_DEVICE_TERMINAL',
                                         'provenance':'OPERATOR_PROVIDED',
                                         'operator_plant_id':plant_id,'feeder_label':feeder_label})
            else:
                for s in fused_named:
                    tpoints={tuple(t.point) for t in s.terminals}
                    # Beta3 graph snaps to 0.35; allow tolerance to match terminals
                    # generated from snapped node locations, but never invent a bridge.
                    hit=_bfs(adj,start,tpoints)
                    if hit is None:
                        result['traces'].append({'status':'UNRESOLVED','reason':'NO_EXTERNAL_GEOMETRIC_PATH',
                                                'target_tag':s.tag,'target_symbol_id':s.symbol_id})
                    else:
                        result['traces'].append({'status':'LOCAL_GEOMETRIC_PATH_CANDIDATE',
                                                'target_tag':s.tag,'target_symbol_id':s.symbol_id,
                                                'target_text_anchor_id':s.text_anchor_id,
                                                'operator_plant_id':plant_id,'operator_feeder_label':feeder_label,
                                                'operator_feeder_point':list(feeder_point),
                                                'path':hit,'verified_electrical':False,
                                                'feeder_membership_asserted':False,
                                                'warning':'A local geometric route is not electrical feeder verification.'})
        result['status']='COMPLETE_DIAGNOSTIC'
        if roi is not None:
            result['notes'].append('ROI_ONLY: route cannot prove full-page feeder connectivity')
        if not fused_named:
            result['notes'].append('No named text+symbol+terminal fusion eligible for operator-root tracing')
        result['notes'].append('Requires independent device/topology verification before electrical membership')
        return result
