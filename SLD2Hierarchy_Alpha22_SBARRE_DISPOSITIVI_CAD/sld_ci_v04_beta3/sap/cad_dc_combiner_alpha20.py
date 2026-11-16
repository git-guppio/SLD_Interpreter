"""Alpha20: classify *graphic* DC combiner-cabinet candidates.

Require three independent cues inside each equally spaced cyan compartment:
 cyan enclosure (already validated by Alpha18), red horizontal DC bus and green
 control/protection symbol. These candidates are NOT automatically 'String Box'
 SAP assets; a QPS-to-StringBox semantic mapping must first be verified.

No ground truth, filename checks, predefined 8/16 cardinality or OCR calls.
"""
from __future__ import annotations

import numpy as np
from .vector_diagnostics_alpha17 import _mask_color


def _cabinet_visual_features(red, green, bbox):
    x1,y1,x2,y2 = (int(n) for n in bbox)
    if x2<=x1 or y2<=y1:
        return None
    red_patch=red[y1:y2,x1:x2]
    green_patch=green[y1:y2,x1:x2]
    if not red_patch.size or not green_patch.size:
        return None
    width=x2-x1
    red_row_max=int(red_patch.sum(axis=1).max())
    green_pixels=int(green_patch.sum())
    red_pixels=int(red_patch.sum())
    has_bus=(red_row_max >= max(8, int(width*.46)) and red_pixels>=max(12,int(width*.7)))
    has_control=green_pixels >= 4
    return {'bbox_px':[x1,y1,x2,y2],
            'red_bus_row_pixels':red_row_max,'red_pixels':red_pixels,
            'green_control_pixels':green_pixels,
            'dc_bus_like':has_bus,'protection_like':has_control,
            'candidate':has_bus and has_control}


def classify_combiner_candidates(image, downstream_fields, panels, *, page_number=1):
    """Classify each detected drawn compartment using two local color features.

    Grouping does not create electrical ownership; returns per-field evidence.
    """
    red=np.asarray(_mask_color(image,'rosso'))>0
    green=np.asarray(_mask_color(image,'verde'))>0
    field_records=[]
    for field in downstream_fields:
        if int(field['page'])!=page_number:
            continue
        matches=[]
        for box in field['panel_boxes_px']:
            panel=next((p for p in panels if int(p.get('page',page_number))==page_number
                        and p['bbox_px']==box),None)
            if panel is None:continue
            n=int(panel['contained_cyan_compartments'])
            if n<1:continue
            x1,y1,x2,y2=box
            for i in range(n):
                bx1=round(x1+(x2-x1)*i/n)
                bx2=round(x1+(x2-x1)*(i+1)/n)
                item=_cabinet_visual_features(red,green,(bx1,y1,bx2,y2))
                if item:
                    item['panel_bbox_px']=list(box)
                    item['cell_ordinal_in_panel']=i+1
                    matches.append(item)
        accepted=[x for x in matches if x['candidate']]
        field_records.append({
            'page':page_number,'field_candidate':field['field_candidate'],
            'graphic_compartments_observed':field['compartments_observed'],
            'dc_combiner_like_cabinet_candidates':len(accepted),
            'all_graphic_compartments_meet_symbol_test':(
                bool(matches) and len(matches)==field['compartments_observed']
                and len(accepted)==len(matches)),
            'candidate_cabinet_evidence':accepted,
            'missing_cue_boxes_px':[x['bbox_px'] for x in matches if not x['candidate']],
            'classification':'PV_DC_COMBINER_LIKE_GRAPHIC_NOT_CONFIRMED_STRING_BOX',
            'string_boxes_verified':None,
            'operator_semantic_mapping_required':True,
        })
    return field_records
