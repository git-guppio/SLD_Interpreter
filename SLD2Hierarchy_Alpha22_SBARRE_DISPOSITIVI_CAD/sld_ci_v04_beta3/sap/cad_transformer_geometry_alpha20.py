"""Vector double-winding circular-symbol candidates without text or GT.

This identifies near-identical overlapping ring shapes in raw native vector
paths, independent of raster antialiasing, colors of enclosures and page
rotation. A double-ring symbol is a *transformer-like visual candidate*, not
proof of its voltage class or connection across an interposed switch.
"""
from __future__ import annotations

import math
import numpy as np


def find_vector_circle_shapes(page, *, raster_width=1000, min_diameter=8,max_diameter=65):
    scale=min(1.0,raster_width/max(page.rect.width,page.rect.height))
    rotation=page.rotation_matrix
    candidates=[]
    for path_index,path in enumerate(page.get_drawings()):
        if path.get('color')!=(0.0,0.0,0.0) or path.get('type')!='s':continue
        bbox=path['rect'];w=bbox.width;h=bbox.height
        if h<=0 or not(min_diameter<=w<=max_diameter and .88<=w/h<=1.12):continue
        lines=[item for item in path.get('items',()) if item[0]=='l']
        if len(lines)<12:continue
        cx=(bbox.x0+bbox.x1)/2;cy=(bbox.y0+bbox.y1)/2
        rr=np.asarray([math.hypot(item[1].x-cx,item[1].y-cy) for item in lines])
        if rr.mean()<=0 or float(rr.std()/rr.mean())>.08:continue
        # Require true 360-degree coverage, not an arc or rounded label glyph.
        angles=sorted(math.atan2(item[1].y-cy,item[1].x-cx) for item in lines)
        gaps=[angles[i+1]-angles[i] for i in range(len(angles)-1)]
        gaps.append((angles[0]+2*math.pi)-angles[-1])
        if max(gaps)>math.pi*.38:continue
        c=type(lines[0][1])(cx,cy)*rotation
        radius=float(rr.mean()*scale)
        shape={'center_px':[float(c.x*scale),float(c.y*scale)],'radius_px':radius,
               'circle_cv':round(float(rr.std()/rr.mean()),5),'pdf_path_index':path_index,
               'source_bbox_pdf':[round(float(z),3) for z in bbox]}
        if any(math.dist(shape['center_px'],other['center_px'])<max(.35,.13*radius)
               and abs(shape['radius_px']-other['radius_px'])<max(.3,.11*radius)
               for other in candidates):
            continue
        candidates.append(shape)
    return candidates


def double_winding_candidates(circles):
    pairs=[]
    for i,a in enumerate(circles):
        for b in circles[i+1:]:
            r1=a['radius_px'];r2=b['radius_px']
            if max(r1,r2)>min(r1,r2)*1.18:continue
            distance=math.dist(a['center_px'],b['center_px'])
            if not (.95*min(r1,r2)<=distance<=1.85*max(r1,r2)):continue
            cx=(a['center_px'][0]+b['center_px'][0])/2
            cy=(a['center_px'][1]+b['center_px'][1])/2
            pairs.append({'center_px':[round(cx,2),round(cy,2)],
                          'ring_centers_px':[a['center_px'],b['center_px']],
                          'source_path_indices':[a['pdf_path_index'],b['pdf_path_index']],
                          'distance_px':round(distance,3),
                          'status':'DOPPIO_AVVOLGIMENTO_GRAFICO_CANDIDATO',
                          'tr_lv_mv_classified':False,'electrical_connection_verified':False})
    return pairs


def candidate_upstream_tr_winding_pairs(pairs,leads,*, max_horizontal_px=22):
    """Find winding pair on axis of independently traced converter feeder leads.

    Never asserts the TR parent; if multiple candidates fit the region, retain
    ambiguity instead of picking the closest.
    """
    traced=[x for x in leads if x.get('upstream_terminal_px') is not None]
    if not traced:return {'status':'NO_TRACED_INPUT_FEEDER','candidates':[], 'tr_parent':None}
    terminals=[x['upstream_terminal_px'] for x in traced]
    terminal_x=sorted(p[0] for p in terminals)[len(terminals)//2]
    terminal_y=min(p[1] for p in terminals)
    options=[p for p in pairs if abs(p['center_px'][0]-terminal_x)<=max_horizontal_px
             and 8<terminal_y-p['center_px'][1]<max(140,terminal_y*.8)]
    return {'status':('ONE_AXIAL_TR_WINDING_HYPOTHESIS' if len(options)==1 else
                      'MULTIPLE_AXIAL_WINDING_HYPOTHESES' if options else
                      'NO_WINDING_PAIR_ON_COMMON_FEEDER_AXIS'),
            'candidates':options,
            'upstream_morsetti_count':len(traced),
            'axial_reference_px':[terminal_x,terminal_y],
            'tr_parent':None, 'electric_path_across_device_verified':False,
            'classification_evidence':'TWO_CIRCULAR_VECTOR_WINDINGS_PLUS_INPUT_FEEDER_AXIS'}
