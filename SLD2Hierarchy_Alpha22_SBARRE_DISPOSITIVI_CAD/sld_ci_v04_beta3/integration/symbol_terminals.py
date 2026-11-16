"""Alpha 7: source-grounded, *candidate-only* symbol / contact inspection.

No inferred symbol, circle pair, text label or nearby vector can establish an
actual equipment instance, terminal, switching state or energized route.
Does not use plant names, benchmark or ground truth. Operates only on already
bounded page-vector ROIs to avoid PV4's 200k+ full-page object explosion.
"""
from __future__ import annotations

import math

SCHEMA = 'sld-beta3-symbol-contacts/v1'


def _dist(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def _bbox_dist(box, point):
    x0,y0,x1,y1=box
    x,y=point
    return math.hypot(max(x0-x,0,x-x1),max(y0-y,0,y-y1))


def _round_rect(b):
    return [round(float(v),3) for v in b]


def _circle_candidates(nearby, roi):
    """Four Bezier segments enclosing near-square shape. Not proven coils."""
    out=[]; seen=set()
    for drawing_id, d in nearby:
        items=d.get('items') or []
        if len(items)!=4 or not all(item[0]=='c' for item in items):
            continue
        box=d.get('rect')
        if box is None:continue
        x0,y0,x1,y1=map(float,box)
        w=x1-x0; h=y1-y0
        if not 7<=w<=55 or not 7<=h<=55 or abs(w-h)>0.10*max(w,h):
            continue
        cx=(x0+x1)/2;cy=(y0+y1)/2
        if not (roi.x0<=cx<=roi.x1 and roi.y0<=cy<=roi.y1):
            continue
        key=(round(cx,2),round(cy,2),round(w,2),round(h,2))
        if key in seen:continue
        seen.add(key)
        out.append({'drawing_id':drawing_id,'center':(cx,cy),
                    'diameter':(w+h)/2,'bbox':(x0,y0,x1,y1)})
    return out


def _pairs(circles, tag_box):
    matches=[]
    for i,a in enumerate(circles):
        for b in circles[i+1:]:
            d1=a['diameter'];d2=b['diameter']; mean=(d1+d2)/2
            ax,ay=a['center'];bx,by=b['center']
            if not 0.80<=d1/d2<=1.25:continue
            # Coupled-ring symbol may be mirrored, horizontal or vertical.
            dx=abs(ax-bx); dy=abs(ay-by)
            along=max(dx,dy); across=min(dx,dy)
            if not (.55*mean<=along<=1.15*mean and across<=.17*mean):continue
            box=[min(a['bbox'][0],b['bbox'][0]),min(a['bbox'][1],b['bbox'][1]),
                 max(a['bbox'][2],b['bbox'][2]),max(a['bbox'][3],b['bbox'][3])]
            # Tag must be spatially attached, but never *identity-confirmed*.
            center=((box[0]+box[2])/2,(box[1]+box[3])/2)
            tag_distance=_bbox_dist(tag_box,center)
            if tag_distance>90:continue
            matches.append({'box':box,'centers':[a['center'],b['center']],
                            'radii':[d1/2,d2/2],
                            'circle_drawing_ids':[a['drawing_id'],b['drawing_id']],
                            'tag_distance_pt':round(tag_distance,3),
                            'pair_alignment':'HORIZONTAL' if dx>dy else 'VERTICAL'})
    return sorted(matches,key=lambda r:(r['tag_distance_pt'],tuple(r['circle_drawing_ids'])))


def _drawing_note_cues(lines, tag_box):
    """Never treat a reference/detail line as proof of an equipment instance."""
    x0,y0,x1,y1=tag_box
    near=[]
    for item in lines:
        a,b,c,d=item['bbox']
        if abs(a-x0)>35 or b>y1+90 or d<y0-12:continue
        text=item['text'].upper().strip()
        if any(word in text for word in ('SEE SHEET','REFER TO SHEET',
                     'FIELD MET STATION','DRAWING ','DWG ','DETAIL ')):
            near.append({'text':item['text'][:90],'bbox':item['bbox']})
    return near[:8]


def _contact_candidates(nearby, pairs, *, page=1, max_contacts=16):
    """Require geometric touch to a circle edge plus line escaping symbol body.

    Intersection/endpoint tolerance here is *diagnostic*, not verified terminal.
    Kept separate from any electrical conductor graph.
    """
    if len(pairs)!=1:return []
    pair=pairs[0];x0,y0,x1,y1=pair['box']
    result=[]
    seen=set()
    for di,d in nearby:
        if d.get('type') not in ('s','fs','sf'):continue
        dash=str(d.get('dashes','[] 0')).strip()
        if dash not in ('[] 0','[] 0.0','None',''):continue
        for j,it in enumerate(d.get('items') or []):
            if it[0]!='l':continue
            p,q=tuple(float(v) for v in it[1]),tuple(float(v) for v in it[2])
            if _dist(p,q)<5:continue
            for near,far in ((p,q),(q,p)):
                if not any(abs(_dist(near,ctr)-r)<=1.25 for ctr,r in zip(pair['centers'],pair['radii'])):
                    continue
                # Contact must escape outer rings' collective bounding rectangle,
                # avoiding internal vectors and graphical winding annotations.
                if (x0-2<=far[0]<=x1+2 and y0-2<=far[1]<=y1+2):
                    continue
                key=(di,j)
                if key not in seen:
                    seen.add(key)
                    result.append({'source_stroke_id':f'P{page}_D{di}_I{j}', 'drawing_id':di,'line_item_index':j,'point':_round_rect(near),
                                   'line_other_endpoint':_round_rect(far),
                                   'status':'POSSIBLE_CIRCLE_EDGE_CONTACT_NOT_TERMINAL',
                                   'terminal_verified':False,'conductor_verified':False})
                break
            if len(result)>=max_contacts:return result
    return result


def inspect_local_tag(dev, nearby, roi, native_text_lines, *, max_contacts=16):
    """Conservative candidate of symbol/terminal, entirely scoped to one tag."""
    typ=dev['tag_type']; tag=dev['tag']; box=dev['bbox']
    notes=_drawing_note_cues(native_text_lines,box)
    output={'schema':SCHEMA,'page':dev['page'],'tag':tag,'tag_type':typ,
            'tag_bbox':box,'tag_source':dev.get('source','NATIVE_PDF_TEXT'),
            'drawing_note_cues':notes,'symbol_hypotheses':[],
            'possible_contact_points':[],
            'symbol_physical_identity_verified':False,
            'device_terminals_verified':0,'through_device_paths_verified':0,
            'feeder_memberships_graph_verified':0,
            'decision':'NO_SUPPORTED_SYMBOL_PATTERN'}
    if typ!='TRANSFORMER_TAG':
        output['decision']='SYMBOL_CLASS_NOT_IMPLEMENTED';return output
    circles=_circle_candidates(nearby,roi)
    pairs=_pairs(circles,box)
    if not pairs:
        output['decision']='DRAWING_NOTE_REVIEW' if notes else 'NO_PAIRED_CIRCLE_SYMBOL'
        return output
    if len(pairs)>1:
        output['decision']='MULTIPLE_SYMBOL_HYPOTHESES_NEEDS_REVIEW'
    else:
        output['decision']='SINGLE_PAIRED_CIRCLE_SYMBOL_CANDIDATE'
    for i,hyp in enumerate(pairs[:8],1):
        output['symbol_hypotheses'].append({'hypothesis_id':f"P{dev['page']}_TAG_{tag}_H{i}",
             'pattern':'TWO_NEAR_EQUAL_ALIGNED_BEZIER_RINGS',
             'bbox':_round_rect(hyp['box']),
             'circle_drawing_ids':hyp['circle_drawing_ids'],
             'tag_distance_pt':hyp['tag_distance_pt'],
             'match_status':'GEOMETRY_AND_TEXT_ASSOCIATION_CANDIDATE_ONLY',
             'physical_device_verified':False})
    # Source-point candidates are not emitted for multiple possible devices.
    if len(pairs)==1:
        output['possible_contact_points']=_contact_candidates(nearby,pairs,page=dev['page'],max_contacts=max_contacts)
    return output
