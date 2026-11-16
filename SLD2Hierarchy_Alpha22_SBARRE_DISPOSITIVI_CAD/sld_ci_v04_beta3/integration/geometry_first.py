"""Alpha8 independent, source-first geometry diagnostic for vector-only drawings.

Only proposes groups of circle-like paths. No tags, assets, terminals or
conductive connectivity are asserted by this geometry-only route.
"""
from __future__ import annotations

from collections import defaultdict
from math import hypot

SCHEMA = 'sld-beta3-geometry-first/v1'
SOLID_DASHES = {'[] 0', '[] 0.0', 'None', ''}


def _circle_like(drawing, drawing_id):
    items=drawing.get('items', ())
    if len(items) not in (4,) and not (20 <= len(items) <= 96):
        return None
    codes={a[0] for a in items}
    if codes not in ({'c'}, {'l'}):
        return None
    if codes=={'c'} and len(items)!=4:
        return None
    if codes=={'l'} and len(items)<20:
        return None
    if drawing.get('type') not in ('s','fs','sf') or str(drawing.get('dashes','[] 0')).strip() not in SOLID_DASHES:
        return None
    box=drawing.get('rect')
    if box is None:return None
    x0,y0,x1,y1=(float(v) for v in box)
    w=x1-x0;h=y1-y0
    if not (7 <= w <= 65 and 7 <= h <= 65 and abs(w-h)<=.08*max(w,h)):
        return None
    center=((x0+x1)/2,(y0+y1)/2)
    radius=(w+h)/4
    if codes=={'l'}:
        # Strictly continuous, closed polygonal approximation of a circle.
        # Reject open dashes, letter outlines, stairways, and jagged symbols.
        points=[];previous=None
        for item in items:
            a,b=item[1],item[2]
            a=(float(a[0]),float(a[1]));b=(float(b[0]),float(b[1]))
            if previous and hypot(previous[0]-a[0],previous[1]-a[1]) > .025*radius:
                return None
            # A skipped arc/large chord must not qualify as a regular polygon.
            if hypot(b[0]-a[0],b[1]-a[1]) > 1.40*2*3.141592653589793*radius/len(items):
                return None
            if not points:points.append(a)
            points.append(b);previous=b
        if hypot(points[-1][0]-points[0][0],points[-1][1]-points[0][1]) > .025*radius:
            return None
        residuals=[abs(hypot(x-center[0],y-center[1])-radius)/radius for x,y in points[:-1]]
        if max(residuals)>.085 or sum(residuals)/len(residuals)>.035:
            return None
    # Four-curve circles are already screened for bbox and declared Bézier arcs.
    return {'drawing_id':int(drawing_id),'bbox':[round(x,3) for x in (x0,y0,x1,y1)],
            'center':[round(c,3) for c in center], 'diameter_pt':round((w+h)/2,3),
            'rendering':'POLYGON_LINES' if codes=={'l'} else 'BEZIER_ARCS',
            'path_item_count':len(items)}


def group_circles(circles, *, page_number, max_groups=30):
    """Locality-limited connected components; outputs hypotheses, not devices."""
    if not circles:return [],0
    # Efficient broadphase: candidates stored in local cells; no all-pairs scan.
    indexed=defaultdict(list);cell_size=70.0
    for i,c in enumerate(circles):
        x,y=c['center'];indexed[(int(x//cell_size),int(y//cell_size))].append(i)
    par=list(range(len(circles)))
    def root(i):
        while par[i]!=i:
            par[i]=par[par[i]];i=par[i]
        return i
    def union(a,b):
        a=root(a);b=root(b)
        if a!=b:par[max(a,b)]=min(a,b)
    for i,a in enumerate(circles):
        x,y=a['center'];bx,by=int(x//cell_size),int(y//cell_size)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for j in indexed.get((bx+dx,by+dy),[]):
                    if j<=i:continue
                    b=circles[j];da=a['diameter_pt'];db=b['diameter_pt'];mean=(da+db)/2
                    if not .82<=da/db<=1.22:continue
                    dist=hypot(x-b['center'][0],y-b['center'][1])
                    if .55*mean<=dist<=1.18*mean:union(i,j)
    components=defaultdict(list)
    for i in range(len(circles)):components[root(i)].append(circles[i])
    candidates=[]
    for component in components.values():
        if not 2<=len(component)<=3:continue
        xs=[v['bbox'][0] for v in component];ys=[v['bbox'][1] for v in component]
        xe=[v['bbox'][2] for v in component];ye=[v['bbox'][3] for v in component]
        renders=sorted({v['rendering'] for v in component})
        candidates.append({'page':page_number,'pattern':f'{len(component)}_NEAR_EQUAL_CIRCULAR_PATHS',
                           'geometry_status':'CANDIDATE_UNLABELED_NOT_EQUIPMENT',
                           'bbox':[min(xs),min(ys),max(xe),max(ye)],
                           'circle_drawing_ids':sorted(v['drawing_id'] for v in component),
                           'rendering_methods':renders, 'source_circles':component,
                           'tag_association_status':'NOT_ATTEMPTED_OR_NOT_CONFIRMED',
                           'asset_verified':False,'terminal_verified':False,'through_device_path_verified':False})
    candidates.sort(key=lambda v:(v['bbox'][1],v['bbox'][0],v['circle_drawing_ids']))
    return candidates[:max_groups],max(0,len(candidates)-max_groups)


def inspect_page_geometry(page, *, page_number, max_drawings=400_000, max_groups=30):
    """Full vector-source circle scan, independent of native text and OCR.

    Explicitly declines pages beyond configured safety budget; never claims
    full source coverage if truncated or rejected.
    """
    drawings=page.get_cdrawings()
    count=len(drawings)
    if count>max_drawings:
        return {'page':page_number,'status':'PAGE_VECTOR_SAFETY_CAP','drawing_count':count,
                'circles_detected':0,'group_count_total':None,'hypotheses':[],
                'omitted_hypotheses':None, 'source_scan_complete':False,
                'physical_assets_verified':0,'device_terminals_verified':0,'graph_verified_feeder_memberships':0}
    circles=[]
    for di,d in enumerate(drawings):
        c=_circle_like(d,di)
        if c:circles.append(c)
    groups, omitted=group_circles(circles,page_number=page_number,max_groups=max_groups)
    return {'page':page_number,'status':'COMPLETE_VECTOR_SHAPE_SCAN' if not omitted else 'SHAPE_SCAN_COMPLETE_REVIEW_BUDGET',
            'drawing_count':count,'circles_detected':len(circles),
            'group_count_total':len(groups)+omitted,'hypotheses':groups,
            'omitted_hypotheses':omitted,'source_scan_complete':True,
            'physical_assets_verified':0,'device_terminals_verified':0,'graph_verified_feeder_memberships':0}
