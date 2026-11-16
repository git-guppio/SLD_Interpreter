"""Independent beta3 vector connectivity kernel. No asset-specific rules or ground truth.

The graph contains conductive strokes only; visual geometry is retained as evidence.
Short strokes are not rejected by a global length cutoff. Decisions use shape/style,
junction evidence and local connectivity. Open breaks stay disconnected.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable
import math
import pymupdf as fitz
import networkx as nx
from .spatial_index import SegmentIndex
from .dash_patterns import find_microdash_candidates

@dataclass(frozen=True)
class Stroke:
    sid: str
    p1: tuple[float,float]
    p2: tuple[float,float]
    color: tuple[float,...] | None
    width: float
    dashed: bool = False
    source_page: int = 1
    def length(self): return math.dist(self.p1,self.p2)

def dist(a,b): return math.dist(a,b)
def snap(p,tol=0.35): return tuple(round(c/tol)*tol for c in p)
def _near(a,b,t=0.5): return dist(a,b)<=t
def _intersects(a,b,tol=1e-7):
    x1,y1=a.p1; x2,y2=a.p2; x3,y3=b.p1; x4,y4=b.p2
    denom=(x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
    if abs(denom)<tol: return None
    px=((x1*y2-y1*x2)*(x3-x4)-(x1-x2)*(x3*y4-y3*x4))/denom
    py=((x1*y2-y1*x2)*(y3-y4)-(y1-y2)*(x3*y4-y3*x4))/denom
    def inside(p,a,b):
        return min(a,b)-tol <= p <= max(a,b)+tol
    if all((inside(px,x1,x2),inside(py,y1,y2),inside(px,x3,x4),inside(py,y3,y4))): return (px,py)
    return None
def _param(s,p):
    dx=s.p2[0]-s.p1[0];dy=s.p2[1]-s.p1[1]
    return ((p[0]-s.p1[0])*dx+(p[1]-s.p1[1])*dy)/max(dx*dx+dy*dy,1e-12)
def _on(s,p,tol=0.35):
    t=_param(s,p)
    if not -tol/max(s.length(),1) <= t <= 1+tol/max(s.length(),1):return False
    q=(s.p1[0]+t*(s.p2[0]-s.p1[0]),s.p1[1]+t*(s.p2[1]-s.p1[1]))
    return dist(q,p)<=tol
def _dots(page):
    result=[]
    for d in page.get_drawings():
        # Filled small circles signal actual junction; unfilled circles do not.
        if d.get('fill') is None:continue
        r=d.get('rect')
        if not r:continue
        w,h=r.width,r.height
        if .4<=w<=7 and .4<=h<=7 and abs(w-h)<=max(.8,.2*w):
            typ=d.get('type','')
            if 'f' in typ:
                result.append(((r.x0+r.x1)/2,(r.y0+r.y1)/2))
    return result
def extract_pdf(page, *, page_number=1):
    strokes=[]; rejected=[]; seen=set()
    for di,d in enumerate(page.get_drawings()):
        items=d.get('items',[])
        dash=d.get('dashes','[] 0')
        dashed=bool(dash and str(dash).strip() not in ('[] 0','[] 0.0','None',''))
        if dashed:
            rejected.append({'drawing':di,'reason':'DASHED_NON_CONDUCTIVE_CANDIDATE'})
            continue
        if d.get('type') not in ('s','fs','sf'):
            continue
        for j,item in enumerate(items):
            if item[0]=='l':
                p,q=item[1],item[2]
                s=Stroke(f'P{page_number}_D{di}_I{j}',(float(p.x),float(p.y)),(float(q.x),float(q.y)),
                         tuple(d['color']) if d.get('color') else None,float(d.get('width',1)),False,page_number)
                key=(di,tuple(sorted((tuple(round(v,5) for v in s.p1),tuple(round(v,5) for v in s.p2)))))
                if key in seen: continue
                seen.add(key)
                if s.length()<1e-7:
                    rejected.append({'sid':s.sid,'reason':'ZERO_LENGTH'})
                else:strokes.append(s)
            elif item[0] not in ('re','c','qu'):
                rejected.append({'drawing':di,'kind':str(item[0]),'reason':'UNSUPPORTED_SHAPE'})
    return strokes,rejected,_dots(page)
def build_graph(strokes:Iterable[Stroke], *,dots=(),tol=0.35,max_strokes=20000):
    strokes=list(strokes)
    warnings=[]
    if len(strokes)>max_strokes:
        return {'status':'INCOMPLETE','warnings':[{'code':'SEGMENT_LIMIT','count':len(strokes),'limit':max_strokes}],
                'node_count':0,'edge_count':0,'component_count':None,'edges':[]}
    active=[s for s in strokes if not s.dashed and s.length()>1e-7]
    rejected=[{'sid':s.sid,'reason':'DASHED_STYLE'} for s in strokes if s.dashed]
    cut={s.sid:[s.p1,s.p2] for s in active}
    crossings=[]
    broadphase=SegmentIndex(active,tolerance=max(tol,0.35))
    candidates_examined=0
    for i,a in enumerate(active):
        for j in sorted(j for j in broadphase.query_indices(a) if j>i):
            b=active[j]
            candidates_examined+=1
            p=_intersects(a,b)
            if p is not None:
                endpoint=(any(_near(p,x,tol) for x in (a.p1,a.p2)) or
                          any(_near(p,x,tol) for x in (b.p1,b.p2)))
                dot=any(_near(p,q,max(tol,1.0)) for q in dots)
                connect=endpoint or dot
                crossings.append({'a':a.sid,'b':b.sid,'point':list(p),'connected':connect,'evidence':'ENDPOINT' if endpoint else ('JUNCTION_DOT' if dot else 'CROSSING_NO_DOT')})
                if connect:
                    cut[a.sid].append(p);cut[b.sid].append(p)
            # Collinear touch and endpoint-to-interior, even for short strokes.
            for point in (a.p1,a.p2):
                if _on(b,point,tol) and _on(a,point,tol):
                    cut[a.sid].append(point);cut[b.sid].append(point)
            for point in (b.p1,b.p2):
                if _on(a,point,tol) and _on(b,point,tol):
                    cut[a.sid].append(point);cut[b.sid].append(point)
    g=nx.Graph()
    edge_evidence=[]
    for s in active:
        pts=sorted(cut[s.sid],key=lambda p:_param(s,p))
        unique=[]
        for p in pts:
            if not unique or dist(p,unique[-1])>tol:unique.append(p)
        for p,q in zip(unique,unique[1:]):
            if dist(p,q)<1e-8: continue
            u,v=snap(p,tol),snap(q,tol)
            if u==v:continue
            g.add_edge(u,v,sid=s.sid)
            edge_evidence.append({'from':list(u),'to':list(v),'source_sid':s.sid})
    return {'status':'COMPLETE','warnings':warnings,'node_count':g.number_of_nodes(),
            'edge_count':g.number_of_edges(),'component_count':nx.number_connected_components(g),
            'components':[sorted([list(p) for p in group]) for group in nx.connected_components(g)],
            'crossings':crossings,'rejected':rejected,'edges':edge_evidence,
            'broadphase_pair_checks':candidates_examined,
            'potential_pairs_without_index':len(active)*(len(active)-1)//2,
            'microdash_pattern_candidates':find_microdash_candidates(active)}
def analyze_pdf(path, page_number=1,max_strokes=20000):
    with fitz.open(str(path)) as doc:
        page=doc[page_number-1]
        strokes,rejected,dots=extract_pdf(page,page_number=page_number)
        res=build_graph(strokes,dots=dots,max_strokes=max_strokes)
        res.update({'source_file':str(path),'page':page_number,'strokes':len(strokes),'junction_dots':len(dots),
                    'ignored_drawings':rejected})
        return res
