"""Evidence-preserving geometry path query, deliberately NOT asset/feeder inference.

Queries require explicit coordinate anchors supplied by an operator or future detector.
Only the previously built (bounded) graph is traversed. No gap bridging or GT.
"""
from __future__ import annotations
from collections import deque
from math import dist
from .kernel import build_graph, extract_pdf
from .classify import classify_strokes
import pymupdf


def trace_between(graph_result, start, end, *, anchor_tolerance=0.6):
    if graph_result.get('status') != 'COMPLETE':
        return {'status':'UNRESOLVED','reason':'GRAPH_INCOMPLETE','path_verified':False}
    edges=graph_result.get('edges',[])
    adjacency={}
    for e in edges:
        a,b=tuple(e['from']),tuple(e['to'])
        adjacency.setdefault(a,[]).append((b,e['source_sid']))
        adjacency.setdefault(b,[]).append((a,e['source_sid']))
    def anchor(pt):
        options=[(dist(pt,p),p) for p in adjacency if dist(pt,p)<=anchor_tolerance]
        return min(options,key=lambda x:x[0])[1] if options else None
    a,b=anchor(start),anchor(end)
    if a is None or b is None:
        return {'status':'UNRESOLVED','reason':'ANCHOR_NOT_ON_GRAPH','path_verified':False,
                'start_resolved':a is not None,'end_resolved':b is not None}
    queue=deque([a]); parent={a:None}; via={}
    while queue:
        node=queue.popleft()
        if node==b:break
        for other,sid in adjacency[node]:
            if other not in parent:
                parent[other]=node;via[other]=sid;queue.append(other)
    if b not in parent:
        return {'status':'DISCONNECTED','reason':'NO_GEOMETRIC_PATH','path_verified':False,
                'start_node':list(a),'end_node':list(b)}
    nodes=[];sids=[];p=b
    while p is not None:
        nodes.append(list(p))
        if p!=a:sids.append(via[p])
        p=parent[p]
    nodes.reverse();sids.reverse()
    return {'status':'PATH_FOUND','path_verified':True,'verification_scope':'VECTOR_GEOMETRY_ONLY',
            'start_node':list(a),'end_node':list(b),'path_nodes':nodes,
            'source_stroke_ids':sids,'edge_count':len(sids),
            'warning':'A geometric path does not establish electrical feeder membership or equipment identity.'}


def query_pdf(pdf_path,page_number,start,end,*,roi=None,max_strokes=1200):
    with pymupdf.open(pdf_path) as pdf:
        if not 1<=page_number<=len(pdf):raise ValueError('Page outside PDF')
        strokes,ignored,dots=extract_pdf(pdf[page_number-1],page_number=page_number)
        selected,inventory=classify_strokes(strokes,roi=roi)
        if roi:
            x0,y0,x1,y1=roi
            dots=[p for p in dots if x0<=p[0]<=x1 and y0<=p[1]<=y1]
        graph=build_graph(selected,dots=dots,max_strokes=max_strokes)
        result=trace_between(graph,start,end)
        return {'schema':'sld-path-query/v1','status':result['status'],
                'input':{'pdf_name':str(pdf_path).replace('\\','/').split('/')[-1],
                         'page':page_number,'start':list(start),'end':list(end),
                         'roi':list(roi) if roi else None},
                'scope':'ROI_ONLY' if roi else 'FULL_PAGE',
                'inventory':{'raw':len(strokes),'retained':len(selected),'counts':inventory['counts']},
                'graph':{'status':graph['status'],'nodes':graph['node_count'],
                         'edges':graph['edge_count'],'components':graph['component_count'],
                         'warnings':graph.get('warnings',[])},
                'trace':result,'ground_truth_used':False,'operator_anchors':True,
                'plant_hierarchy_inferred':False,'feeder_membership_inferred':False}
