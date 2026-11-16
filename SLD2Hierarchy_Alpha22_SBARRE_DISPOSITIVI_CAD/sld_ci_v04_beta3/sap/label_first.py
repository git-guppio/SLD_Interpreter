"""Alpha10: document-first PV central inverter hierarchy diagnostics.

Native positional labels produce *candidates*, not automatically verified assets.
No Ground Truth files are read by this engine.  Counts such as '10 STRING BOX'
are documentary quantities, not ten visually identified individual objects.

Plant-scoped, explicitly selected operator confirmations may supply transformer
parentage, without asserting electrical continuity or generalising across sites.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

SCHEMA = 'sld-sap-label-first-alpha10/v1'
REVIEW_SCHEMA = 'sld-sap-alpha10-reviewed-parentage/v1'


def _at(words, i):
    return (round(words[i][0], 2), round(words[i][1], 2))


def _native_page(page, page_number):
    words = page.get_text('words')
    cus, inverters, transformers, boxes = [], [], [], []
    for i, w in enumerate(words):
        value = str(w[4])
        nxt = str(words[i + 1][4]) if i+1 < len(words) else ''
        same_block = i+1 < len(words) and w[5] == words[i+1][5]
        same_line = same_block and w[6] == words[i+1][6]
        # Some CAD generators rotate lettering.  Separate consecutive words
        # remain in the same text block even if not in a conventional row.
        if value.upper() == 'C' and same_block and re.fullmatch(r'\d{1,4}', nxt):
            cus.append({'number':int(nxt),'xy':_at(words,i),'page':page_number,
                        'bbox':list(map(lambda v:round(v,2),(w[0],w[1],words[i+1][2],words[i+1][3])))})
        if value.upper() == 'I' and same_block and re.fullmatch(r'\d{1,4}\.\d{1,3}',nxt):
            major,minor = map(int,nxt.split('.'))
            inverters.append({'printed_cu':major,'slot':minor,'tag':f'I {nxt}',
                              'xy':_at(words,i),'page':page_number})
        if value.upper() == 'TRANSFORMER' and nxt == '1.700' and same_block:
            transformers.append({'xy':_at(words,i),'page':page_number,
                                 'tag':'TRANSFORMER 1.700 kVA'})
        # Only an explicit quantity label is eligible.  Never count
        # individual SB devices by multiplying inferred geometric cells.
        if re.fullmatch(r'\d{1,4}',value) and nxt.upper() == 'STRING' and same_block:
            if i+2 < len(words) and str(words[i+2][4]).upper() == 'BOX' and words[i+2][5] == w[5]:
                boxes.append({'quantity':int(value),'xy':_at(words,i),'page':page_number,
                              'tag':f'{value} STRING BOX'})
    return {'cus':cus,'inverters':inverters,'transformers':transformers,'boxes':boxes,
            'native_text_available':bool(page.get_text('text').strip()),
            'native_words':len(words)}


def _nearest_cu(cus, xy):
    # This is a *bounded locality* rule, NOT a global nearest label.  It
    # rejects nearby but unrelated blocks in dense SLDs.
    candidates=[]
    x,y=xy
    for cu in cus:
        cx,cy=cu['xy']
        dx,dy=cx-x,y-cy
        if -20 <= dx <= 270 and 95 <= dy <= 255:
            candidates.append((abs(dx-110)+abs(dy-180)*0.2,cu))
    candidates.sort(key=lambda a:a[0])
    if not candidates or (len(candidates)>1 and abs(candidates[0][0]-candidates[1][0]) < 5):
        return None
    return candidates[0][1]


def _tr_cu(cus, xy):
    x,y=xy;candidates=[]
    for cu in cus:
        cx,cy=cu['xy'];dx=cx-x;dy=y-cy
        if -30 <= dx <= 145 and 35 <= dy <= 150:
            candidates.append((abs(dx-55)+abs(dy-85)*0.1,cu))
    candidates.sort(key=lambda a:a[0])
    return candidates[0][1] if candidates and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>5) else None


def _assign_box(inverters, box):
    # Explicit CAD labels on this corpus lie on a roughly parallel rail
    # next to their inverter. This is spatial evidence, not conductivity.
    x,y=box['xy']
    matches=[]
    for inv in inverters:
        if inv['page'] != box['page']:
            continue
        ix,iy=inv['xy'];dx=x-ix;dy=y-iy
        if 20 < dx < 44 and 55 < dy < 200:
            matches.append((abs(dx-31.45)+0.05*abs(dy-107),inv))
    matches.sort(key=lambda c:c[0])
    if len(matches)==1 or (len(matches)>1 and matches[1][0]-matches[0][0] > 8):
        return matches[0][1]
    return None


def _id(plant, typ, *parts):
    return f'{plant}::{typ}::'+'.'.join(str(p).zfill(2) for p in parts)


def extract_candidates(pdf_path:str|Path, plant_id:str, review:dict|None=None):
    """Extract labels and positional candidate parents without external GT."""
    pdf_path=Path(pdf_path)
    if not pdf_path.is_file(): raise FileNotFoundError(pdf_path)
    plant = plant_id if str(plant_id).startswith('CI::') else 'CI::'+str(plant_id)
    with pymupdf.open(pdf_path) as pdf:
        pages=[]; cus=[];inv=[];trs=[];sbs=[]
        for ix, page in enumerate(pdf,1):
            x=_native_page(page,ix)
            cus+=x['cus'];inv+=x['inverters'];trs+=x['transformers'];sbs+=x['boxes']
            pages.append({'page':ix,'native_text_available':x['native_text_available'],
                          'native_words':x['native_words'],
                          'vector_drawing_count':len(page.get_drawings())})
    # CU identifiers may be repeated on several drawings; no double counting.
    cu_by_number={};issues=[]
    for cu in cus:
        n=cu['number']
        if n in cu_by_number:
            issues.append({'reason':'REPEATED_CU_TAG','cue':f'C {n}','page':cu['page'],
                           'status':'REVIEW'});continue
        cu_by_number[n]=cu
    nodes=[]; cu_nodes={}
    for n,cu in sorted(cu_by_number.items()):
        row={'asset_id':_id(plant,'CU',n),'type':'CONVERSION_UNIT','parent_id':plant,
             'tag':f'C {n}','source_status':'NATIVE_TEXT_LABEL',
             'evidence_ref':f'{pdf_path.name}:p{cu["page"]}:C {n}:xy={cu["xy"]}',
             'page':cu['page'],'x':cu['xy'][0],'y':cu['xy'][1],
             'quantity':1,'parentage':'DOCUMENT_LOCAL_LABEL'}
        nodes.append(row);cu_nodes[n]=row
    tr_by_cu=defaultdict(list)
    for tr in trs:
        cu=_tr_cu(list(cu_by_number.values()),tr['xy'])
        if cu is None:
            issues.append({'reason':'TRANSFORMER_CU_UNRESOLVED','cue':tr['tag'],
                           'page':tr['page'],'xy':tr['xy'],'status':'REVIEW'});continue
        tr_by_cu[cu['number']].append(tr)
    for n,items in tr_by_cu.items():
        for slot, tr in enumerate(sorted(items,key=lambda a:-a['xy'][0]),1):
            tr['slot']=slot
            nodes.append({'asset_id':_id(plant,'TR',n,slot),'type':'MV_LV_TRANSFORMER',
                          'parent_id':cu_nodes[n]['asset_id'],'tag':f'TR {slot}',
                          'source_status':'NATIVE_TRANSFORMER_LABEL_CANDIDATE',
                          'evidence_ref':f'{pdf_path.name}:p{tr["page"]}:{tr["tag"]}:xy={tr["xy"]}',
                          'page':tr['page'],'x':tr['xy'][0],'y':tr['xy'][1],
                          'quantity':1,'parentage':'SPATIAL_CU_CANDIDATE'})
    for x in inv:
        cu=_nearest_cu(list(cu_by_number.values()),x['xy'])
        x['assigned_cu']=cu['number'] if cu else None
        n=x['assigned_cu']; slot=x['slot']
        if n is None:
            issues.append({'reason':'INVERTER_CU_UNRESOLVED','cue':x['tag'],
                           'page':x['page'],'xy':x['xy'],'status':'REVIEW'});continue
        if x['printed_cu'] != n:
            issues.append({'reason':'INVERTER_PRINTED_ID_CONFLICT','cue':x['tag'],
                           'expected_cu':n,'page':x['page'],'xy':x['xy'],'status':'REVIEW'})
        # Unique position-local name, even when the printed CU prefix has a typo.
        aid=_id(plant,'INV',n,slot)
        if any(z['asset_id']==aid for z in nodes):
            issues.append({'reason':'DUPLICATE_INVERTER_SLOT','cue':x['tag'],'status':'REVIEW'});continue
        x['asset_id']=aid
        nodes.append({'asset_id':aid,'type':'CENTRAL_INVERTER','parent_id':None,
                      'cu_context_id':cu_nodes[n]['asset_id'],'tag':x['tag'],
                      'source_status':'NATIVE_INVERTER_LABEL_CANDIDATE' if x['printed_cu']==n else 'NATIVE_LABEL_CONFLICT_LOCAL_CANDIDATE',
                      'evidence_ref':f'{pdf_path.name}:p{x["page"]}:{x["tag"]}:xy={x["xy"]}',
                      'page':x['page'],'x':x['xy'][0],'y':x['xy'][1],
                      'quantity':1,'parentage':'TR_PARENT_REQUIRES_CONFIRMATION'})
    valid_inv=[x for x in inv if x.get('asset_id')]
    sb_match_count=Counter();sb_label_count=Counter()
    for sb in sbs:
        found=_assign_box(valid_inv,sb)
        if not found:
            issues.append({'reason':'STRING_BOX_INVERTER_UNRESOLVED','cue':sb['tag'],
                           'page':sb['page'],'xy':sb['xy'],'status':'REVIEW'});continue
        aid=found['asset_id']; sb_match_count[aid]+=1;sb_label_count[aid]+=sb['quantity']
        nodes.append({'asset_id':_id(plant,'SB_QUANTITY',found['assigned_cu'],found['slot']),
                      'type':'STRING_BOX_QUANTITY','parent_id':aid,'tag':sb['tag'],
                      'source_status':'NATIVE_QUANTITY_LABEL_SPATIAL_CANDIDATE',
                      'evidence_ref':f'{pdf_path.name}:p{sb["page"]}:{sb["tag"]}:xy={sb["xy"]}',
                      'page':sb['page'],'x':sb['xy'][0],'y':sb['xy'][1],
                      'quantity':sb['quantity'],'parentage':'NEAREST_INVERTER_LABEL_CANDIDATE'})
    for aid, n in sb_match_count.items():
        if n > 1:
            issues.append({'reason':'MULTIPLE_STRING_BOX_QUANTITIES_FOR_INVERTER',
                           'asset_id':aid,'status':'REVIEW'})
    # Review can only confirm explicitly listed CU/transformer/inverter slots.
    if review is not None:
        if review.get('schema')!=REVIEW_SCHEMA or review.get('plant_id')!=plant:
            raise ValueError('Review schema o plant_id incompatibile')
        idx={x['asset_id']:x for x in nodes};already=set()
        for r in review.get('confirmed_tr_inverter_groups',[]):
            ev=r.get('evidence_ref')
            if not isinstance(ev,str) or not ev.strip():raise ValueError('Manca evidence_ref in conferma HITL')
            cids=r.get('cu_ids')
            if not isinstance(cids,list) or not cids or len(set(map(str,cids)))!=len(cids):
                raise ValueError('cu_ids devono essere un elenco esplicito e senza duplicati')
            t=r.get('transformer_slot'); invslots=r.get('inverter_slots')
            if not isinstance(t,int) or t<1 or not isinstance(invslots,list) or not invslots or not all(isinstance(i,int) and i>0 for i in invslots):
                raise ValueError('Slot trasformatore/inverter non validi')
            for cu in cids:
                tr_id=_id(plant,'TR',int(cu),t)
                if tr_id not in idx:raise ValueError(f'TR non esistente {tr_id}')
                for slot in invslots:
                    inv_id=_id(plant,'INV',int(cu),slot)
                    if inv_id not in idx:raise ValueError(f'Inverter non esistente {inv_id}')
                    if inv_id in already:raise ValueError('Inverter gia assegnato da review')
                    already.add(inv_id);idx[inv_id]['parent_id']=tr_id
                    idx[inv_id]['parentage']='OPERATOR_CONFIRMED_TR_PARENT'
                    idx[inv_id]['operator_evidence_ref']=ev.strip()
    # The operator may explicitly identify a few assets on an otherwise
    # textless/vector-only PDF (e.g. Settimo).  No auto-expansion from GT,
    # no default minima and no unscoped reusable plant patterns.
    if review is not None:
        idx={z['asset_id']:z for z in nodes}
        for r in review.get('confirmed_assets',[]):
            if not isinstance(r,dict):raise ValueError('confirmed_assets richiede oggetti')
            typ=r.get('type'); aid=r.get('asset_id'); parent=r.get('parent_id')
            ev=r.get('evidence_ref'); q=r.get('quantity',1)
            if typ not in ('CONVERSION_UNIT','MV_LV_TRANSFORMER','CENTRAL_INVERTER',
                           'IOCB','LV_LV_TRANSFORMER','STRING_BOX_QUANTITY'):
                raise ValueError('Tipo asset confermato non ammesso')
            if not isinstance(aid,str) or not aid.startswith(plant+'::') or aid in idx:
                raise ValueError('ID asset non univoco o non scoped sul plant: '+str(aid))
            if not isinstance(ev,str) or not ev.strip():raise ValueError('evidence_ref mancante')
            if not isinstance(q,int) or isinstance(q,bool) or q<1 or (typ!='STRING_BOX_QUANTITY' and q!=1):
                raise ValueError('Quantita non valida: solo STRING_BOX_QUANTITY puo indicare un gruppo')
            if typ=='CONVERSION_UNIT':
                if parent!=plant:raise ValueError('CU deve avere parent=plant_id')
            else:
                valid_parents={'MV_LV_TRANSFORMER':'CONVERSION_UNIT','IOCB':'CONVERSION_UNIT',
                               'CENTRAL_INVERTER':'MV_LV_TRANSFORMER',
                               'LV_LV_TRANSFORMER':'CENTRAL_INVERTER',
                               'STRING_BOX_QUANTITY':'CENTRAL_INVERTER'}
                # For an inverter with unknown TR parent, record CU context
                # explicitly without inventing a transformer relation.
                if typ=='CENTRAL_INVERTER' and parent is None:
                    cu_context=r.get('cu_context_id')
                    if cu_context not in idx or idx[cu_context]['type']!='CONVERSION_UNIT':
                        raise ValueError('Inverter senza TR: cu_context_id CU confermata necessaria')
                elif parent not in idx or idx[parent]['type']!=valid_parents[typ]:
                    raise ValueError('Tipo parent non valido per '+str(aid))
            node={'asset_id':aid,'type':typ,'parent_id':parent,
                  'tag':str(r.get('tag') or ''),'quantity':q,
                  'source_status':'OPERATOR_CONFIRMED','parentage':'EXPLICIT_OPERATOR_CONFIRMATION',
                  'evidence_ref':ev.strip(),'page':r.get('page') or '',
                  'x':'','y':''}
            if r.get('cu_context_id'): node['cu_context_id']=r['cu_context_id']
            idx[aid]=node;nodes.append(node)
    # Recompute summary from candidates AND explicit operator confirmations.
    # A missing minimum is a review issue, never an inferred extra asset.
    parent_groups=defaultdict(Counter)
    for node in nodes:
        parent_groups[node.get('parent_id')][node['type']]+=1
    if not any(z['type']=='CONVERSION_UNIT' for z in nodes):
        issues.append({'reason':'NO_CU_NATIVE_LABELS_OCR_OR_HITL_REQUIRED','status':'HITL_REQUIRED'})
    for node in nodes:
        if node['type']=='CONVERSION_UNIT':
            for typ in ('IOCB','MV_LV_TRANSFORMER'):
                if not parent_groups[node['asset_id']][typ]:
                    issues.append({'reason':typ+'_NOT_RESOLVED','asset_id':node['asset_id'],'status':'HITL_REQUIRED'})
        elif node['type']=='CENTRAL_INVERTER':
            for typ in ('LV_LV_TRANSFORMER','STRING_BOX_QUANTITY'):
                if not parent_groups[node['asset_id']][typ]:
                    issues.append({'reason':typ+'_NOT_RESOLVED','asset_id':node['asset_id'],'status':'HITL_REQUIRED'})
    parent_missing=sum(1 for x in nodes if x['type']=='CENTRAL_INVERTER' and not x['parent_id'])
    for x in nodes:
        if x['type']=='CENTRAL_INVERTER' and not x['parent_id']:
            issues.append({'reason':'TR_INVERTER_PARENT_NOT_CONFIRMED','asset_id':x['asset_id'],
                           'status':'HITL_REQUIRED'})
    known_cu=sum(1 for x in nodes if x['type']=='CONVERSION_UNIT')
    known_tr=sum(1 for x in nodes if x['type']=='MV_LV_TRANSFORMER')
    known_inv=sum(1 for x in nodes if x['type']=='CENTRAL_INVERTER')
    return {
        'schema':SCHEMA,'plant_id':plant,'source_pdf':str(pdf_path),
        'source_pages':pages,'assets':nodes,'issues':issues,
        'review_applied':review is not None,
        'status':'NEEDS_GEOMETRY_OCR_OR_HITL' if not known_cu else 'HITL_REQUIRED' if issues else 'DOCUMENTARY_HIERARCHY_STAGED',
        'summary':{'cu_labels':known_cu,'transformer_label_candidates':known_tr,
                   'inverter_label_candidates':known_inv,
                   'string_box_quantity_labels_matched':sum(sb_match_count.values()),
                   'string_boxes_documentary_quantity_matched':sum(x['quantity'] for x in nodes if x['type']=='STRING_BOX_QUANTITY'),
                   'string_box_quantity_labels_all':len(sbs),
                   'string_box_documentary_quantity_all':sum(x['quantity'] for x in sbs),
                   'unconfirmed_inverter_transformer_parents':parent_missing,
                   'issues':len(issues)},
        'provenance_policy':'Native text and bounded local geometry only. No GT injection, no electrical continuity claim.',
        'matrix_flow_import_ready':False,
        'sap_functional_locations_generated':False,
    }


def write_outputs(result:dict, directory:str|Path):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    (out/'alpha10_hierarchy_review.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    fields=['asset_id','type','parent_id','cu_context_id','tag','quantity','source_status',
            'parentage','evidence_ref','operator_evidence_ref','page','x','y']
    with (out/'alpha10_asset_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=';');w.writeheader()
        for a in result['assets']:w.writerow({k:a.get(k,'') for k in fields})
    fields=['reason','cue','expected_cu','asset_id','page','xy','status']
    with (out/'alpha10_review_tasks.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=';');w.writeheader()
        for a in result['issues']:w.writerow({k:a.get(k,'') for k in fields})
    # Explicit per-scope counts: no row implies a missing physical device.
    per_parent=defaultdict(list)
    for a in result['assets']:
        per_parent[a.get('parent_id')].append(a)
    scope_fields=['scope_id','scope_type','cu_context_id','tr_candidates','inverter_candidates',
                  'iocb_confirmed','lv_lv_confirmed','string_box_quantity_documentary','unconfirmed_tr_parent']
    with (out/'alpha10_scope_counts.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=scope_fields,delimiter=';');w.writeheader()
        for a in result['assets']:
            if a['type'] not in ('CONVERSION_UNIT','CENTRAL_INVERTER'):continue
            children=per_parent[a['asset_id']];cu=a['asset_id']
            if a['type']=='CONVERSION_UNIT':
                inv=[z for z in result['assets'] if z['type']=='CENTRAL_INVERTER' and
                    (z.get('cu_context_id')==cu or z.get('parent_id') in
                     [p['asset_id'] for p in children if p['type']=='MV_LV_TRANSFORMER'])]
                w.writerow({'scope_id':cu,'scope_type':a['type'],
                            'tr_candidates':sum(z['type']=='MV_LV_TRANSFORMER' for z in children),
                            'inverter_candidates':len(inv),
                            'iocb_confirmed':sum(z['type']=='IOCB' for z in children),
                            'unconfirmed_tr_parent':sum(z['parent_id'] is None for z in inv)})
            else:
                w.writerow({'scope_id':a['asset_id'],'scope_type':a['type'],
                            'cu_context_id':a.get('cu_context_id',''),
                            'lv_lv_confirmed':sum(z['type']=='LV_LV_TRANSFORMER' for z in children),
                            'string_box_quantity_documentary':sum(z['quantity'] for z in children if z['type']=='STRING_BOX_QUANTITY'),
                            'unconfirmed_tr_parent':int(a['parent_id'] is None)})
    with (out/'alpha10_review_groups.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['reason','tasks'])
        w.writerows(sorted(Counter(a['reason'] for a in result['issues']).items()))
    tmpl={'schema':REVIEW_SCHEMA,'plant_id':result['plant_id'],
          'instructions':'Compilare SOLO CU e slot verificati nello SLD, con riferimento grafico esplicito. Non importare i conteggi GT nel motore.',
          'confirmed_tr_inverter_groups':[], 'confirmed_assets':[]}
    (out/'alpha10_operator_review_TEMPLATE.json').write_text(json.dumps(tmpl,indent=2,ensure_ascii=False),encoding='utf-8')
    return out
