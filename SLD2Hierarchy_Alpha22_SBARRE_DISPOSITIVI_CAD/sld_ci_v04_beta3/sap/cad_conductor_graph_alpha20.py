"""Alpha20: source-grounded conductor-run diagnostics on CAD vector SLDs.

A solid-line run can be verified geometrically **up to the next interruption**.
A gap, switch, transformer, crossing without terminal, dashed control line or
unknown device is never bridged. This is NOT transformer/inverter verification,
SAP location creation or a count of string boxes.

No plant names, reference inventories, preconfigured fanouts or TXT are read.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import json
import math
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from PIL import ImageDraw, ImageFont
from .vector_relations_alpha19 import inspect_cad_relations, write_cad_relation_outputs
from .cad_dc_combiner_alpha20 import classify_combiner_candidates
from .vector_diagnostics_alpha17 import _render
from .cad_qps_ocr_alpha20 import recognize_qps_once
from .cad_transformer_geometry_alpha20 import (find_vector_circle_shapes, double_winding_candidates,
                                                     candidate_upstream_tr_winding_pairs)


def _point(p):
    return (float(p[0]), float(p[1]))


def _distance(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


def _point_on_segment(p, a, b, tol=0.75):
    """Strict nearest point on a stroke. Not a conductor-junction assertion."""
    dx=b[0]-a[0];dy=b[1]-a[1]
    ll=dx*dx+dy*dy
    if ll<1e-9: return False
    t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/ll
    if t < -1e-7 or t > 1+1e-7:return False
    return _distance(p,(a[0]+max(0,min(1,t))*dx,a[1]+max(0,min(1,t))*dy))<=tol


def _horizontal_or_vertical(a,b,tol=0.35):
    return abs(a[0]-b[0])<=tol or abs(a[1]-b[1])<=tol


def extract_solid_conductors(page, *, target_width=1000, min_length=3.0):
    """Extract orthogonal uninterrupted black strokes in rendered page coords.

    No gray/colored/dashed paths, polygon outlines, curves, source-text glyphs
    or generated raster lines become electrical evidence automatically.
    """
    scale=min(1.0,target_width/max(page.rect.width,page.rect.height))
    transform=page.rotation_matrix
    out=[]
    for path in page.get_drawings():
        if path.get('color')!=(0.0,0.0,0.0):continue
        if path.get('dashes') not in ('[] 0',None):continue
        width=path.get('width')
        if width is None or not 0 < width <= 5:continue
        for item in path.get('items',()):
            if item[0]!='l':continue
            p=item[1]*transform;q=item[2]*transform
            a=(float(p.x)*scale,float(p.y)*scale)
            b=(float(q.x)*scale,float(q.y)*scale)
            if _distance(a,b)<min_length:continue
            if not _horizontal_or_vertical(a,b):continue
            out.append((a,b))
    return out


def _neighbor_pairs(strokes,tol=0.55):
    """Only explicit common endpoints form graph edges.

    An endpoint meeting the *interior* of a transverse stroke without a dot is
    ambiguous in SLDs; in this version it is deliberately NOT bridged.
    Non-endpoint intersections are never joined. This conservative policy
    can miss genuine T junctions rather than create false continuity.
    """
    groups=defaultdict(list)
    step=max(tol,0.3)
    for i,(a,b) in enumerate(strokes):
        for end in (a,b):
            k=(round(end[0]/step),round(end[1]/step))
            groups[k].append((i,end))
    pairs=set()
    for (gx,gy),items in groups.items():
        vicinity=[]
        for dx in (-1,0,1):
            for dy in (-1,0,1):vicinity.extend(groups.get((gx+dx,gy+dy),()))
        for i,a in items:
            for j,b in vicinity:
                if i<j and _distance(a,b)<=tol:pairs.add((i,j))
    return pairs


def conductor_components(strokes,*,tol=0.55):
    parent=list(range(len(strokes)))
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,j in _neighbor_pairs(strokes,tol):
        a=root(i);b=root(j)
        if a!=b:parent[b]=a
    out=defaultdict(list)
    for i in range(len(strokes)):out[root(i)].append(i)
    return tuple(out.values())


def _lead_anchor(converter,strokes, max_gap=2.1):
    """Return vertical solid stroke meeting top-center converter boundary."""
    x1,y1,x2,_=converter['bbox_px'];cx=(x1+x2)/2;w=x2-x1
    candidates=[]
    for i,(a,b) in enumerate(strokes):
        if abs(a[0]-b[0])>0.45:continue
        xx=(a[0]+b[0])/2
        if abs(xx-cx)>max(5,0.24*w):continue
        low=max(a[1],b[1]);high=min(a[1],b[1])
        if abs(low-y1)<=max_gap and high<=y1-3:
            candidates.append((abs(low-y1),abs(xx-cx),i))
    if not candidates:return None
    candidates.sort()
    if len(candidates)>1 and candidates[0][:2]==candidates[1][:2]:return None
    return candidates[0][2]


def _free_endpoints(strokes,indices,tol=.65):
    """Endpoints of this component with no neighboring segment endpoint."""
    ends=[]
    for i in indices:
        for p in strokes[i]:
            connected=sum(_distance(p,q)<=tol for j in indices for q in strokes[j])
            if connected==1:ends.append(p)
    return ends


def trace_converter_inputs(converters, strokes, *, page_number=1):
    components=conductor_components(strokes)
    belonging={index:tuple(c) for c in components for index in c}
    rows=[]
    for c in converters:
        if int(c.get('page',page_number))!=page_number:continue
        anchor_i=_lead_anchor(c,strokes)
        if anchor_i is None:
            rows.append({'page':page_number,'converter_candidate_id':c['candidate_id'],
                         'status':'NO_UNINTERRUPTED_BLACK_INPUT_LEAD',
                         'upstream_terminal_px':None,'input_anchor_px':None,
                         'segments_in_run':0,'conductor_length_px':0,
                         'evidence_segments_px':[],
                         'tr_parent':None,'electrical_path_verified':False})
            continue
        comp=belonging[anchor_i]
        ends=_free_endpoints(strokes,comp)
        x1,y1,x2,_=c['bbox_px'];cx=(x1+x2)/2
        upstream=[p for p in ends if p[1]<y1-1]
        if upstream:
            # Choose furthest-upstream terminal. Where multiple endpoints
            # at the same level, require the operator to select a parent.
            terminal=min(upstream,key=lambda p:(p[1],abs(p[0]-cx)))
            mode='SOLID_CONDUCTOR_TO_OPEN_UPSTREAM_TERMINAL'
        else:
            terminal=None;mode='INPUT_LEAD_NO_DETERMINATE_UPSTREAM_TERMINAL'
        rows.append({'page':page_number,'converter_candidate_id':c['candidate_id'],
                     'status':mode,'upstream_terminal_px':list(terminal) if terminal else None,
                     'input_anchor_px':list(strokes[anchor_i][0]),
                     'segments_in_run':len(comp),
                     'conductor_length_px':round(sum(_distance(*strokes[i]) for i in comp),2),
                     'evidence_segments_px':[[list(strokes[i][0]),list(strokes[i][1])] for i in comp],
                     'tr_parent':None,'electrical_path_verified':False})
    # Grouping only if *individual* conductor leads terminate on distinct
    # points at the same upstream y-level; never assign a TR from grouping.
    valid=[r for r in rows if r['upstream_terminal_px'] is not None]
    for r in rows:
        siblings=[s['converter_candidate_id'] for s in valid
                  if s is not r and abs(s['upstream_terminal_px'][1]-r['upstream_terminal_px'][1])<=1.8]
        r['co_aligned_termination_other_inverters']=siblings if r['upstream_terminal_px'] else []
    return rows


def inspect_cad_conductor_runs(pdf_path, max_pages=3, *, local_ocr=True, tesseract_executable=None):
    base,previews,prior=inspect_cad_relations(pdf_path,max_pages=max_pages)
    by_page=defaultdict(list)
    for c in base['converter_candidates']:by_page[int(c['page'])].append(c)
    results=[]
    cabinet_evidence=[]
    tr_winding_evidence=[]
    by_field=defaultdict(list)
    for f in base['downstream_field_candidates']:by_field[int(f['page'])].append(f)
    by_panel=defaultdict(list)
    for panel in base['downstream_graphic_panels']:by_panel[int(panel['page'])].append(panel)
    with fitz.open(str(pdf_path)) as pdf:
        for page_i,candidates in by_page.items():
            segs=extract_solid_conductors(pdf[page_i-1])
            leads=trace_converter_inputs(candidates,segs,page_number=page_i)
            results.extend(leads)
            rings=find_vector_circle_shapes(pdf[page_i-1])
            doubles=double_winding_candidates(rings)
            tr_winding_evidence.append({'page':page_i,
                                       'circle_shapes_detected':len(rings),
                                       'winding_pairs_detected':len(doubles),
                                       'local_upstream_winding_hypotheses':candidate_upstream_tr_winding_pairs(doubles,leads)})
            cabinet_evidence.extend(classify_combiner_candidates(_render(pdf[page_i-1]),
                                     by_field.get(page_i,[]),by_panel.get(page_i,[]),page_number=page_i))
    first_page_cabinets=[r for r in cabinet_evidence if r['page']==1]
    ocr_evidence=(recognize_qps_once(pdf_path,first_page_cabinets,executable=tesseract_executable)
                  if local_ocr and first_page_cabinets else {'status':'DISABLED_OR_NO_CABINETS',
                                                    'ocr_calls':0,'tokens':[],'field_sequences':[]})
    report={'schema':'sld-alpha20-conductor-terminals/v1','source_pdf':str(Path(pdf_path)),
            'status':'OPEN_WIRE_RUNS_ONLY_NOT_TRANSFORMER_HIERARCHY',
            'evidence_source':'native_PDF_black_solid_vector_line_segments',
            'source_ground_truth_used':False,'source_txt_used':False,
            'input_conductor_runs':results,
            'dc_combiner_graphic_evidence':cabinet_evidence,
            'local_ocr_qps_evidence':ocr_evidence,
            'transformer_winding_geometry_evidence':tr_winding_evidence,
            'summary':{'converter_like_candidates':len(base['converter_candidates']),
                       'source_continuous_input_leads':sum(r['segments_in_run']>0 for r in results),
                       'upstream_terminal_observed':sum(r['upstream_terminal_px'] is not None for r in results),
                       'dc_combiner_like_cabinets':sum(r['dc_combiner_like_cabinet_candidates'] for r in cabinet_evidence),
                       'qps_cabinet_identifiers_correlated':ocr_evidence.get('qps_cabinets_correlated'),
                       'tr_winding_axial_candidate_count':sum(len(r['local_upstream_winding_hypotheses']['candidates']) for r in tr_winding_evidence),
                       'tr_parent_connections_verified':0,
                       'string_boxes_quantified':None,'sap_hierarchy_ready':False,
                       'matrix_flow_import_ready':False},
            'caveat':'Una traccia di cavo fino a morsetto aperto NON prova il padre TR. '
                     'Non attraversa switch, dispositivi, incroci o lacune; nessuna SB fabbricata.'}
    return base,previews,prior,report


def write_cad_conductor_outputs(base,previews,prior,report,out_dir):
    dest=write_cad_relation_outputs(base,previews,prior,out_dir)
    (dest/'alpha20_conduttori_ingresso.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    with (dest/'alpha20_morsetti_ingresso.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        writer=csv.writer(fh,delimiter=';')
        writer.writerow(['pagina','candidato_inverter','tratta_solid_black','morsetto_monte_xy_px',
                         'segmenti_tracciati','lunghezza_px','altri_inverter_con_morsetto_allineato',
                         'trasformatore_padre','stato_elettrico'])
        for r in report['input_conductor_runs']:
            writer.writerow([r['page'],r['converter_candidate_id'],r['status'],
                             json.dumps(r['upstream_terminal_px']) if r['upstream_terminal_px'] else '',
                             r['segments_in_run'],r['conductor_length_px'],
                             ','.join(r['co_aligned_termination_other_inverters']),
                             '', 'MORSETTO_CANDIDATO_NON_COLLEGAMENTO_TR'])
    with (dest/'alpha20_cabinet_candidati.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        writer=csv.writer(fh,delimiter=';')
        writer.writerow(['pagina','campo_grafico','cabinet_dc_candidati','compartimenti_grafici',
                         'test_simboli_completo','string_box_verificate','stato'])
        for item in report.get('dc_combiner_graphic_evidence',[]):
            writer.writerow([item['page'],item['field_candidate'],
                             item['dc_combiner_like_cabinet_candidates'],
                             item['graphic_compartments_observed'],
                             'SI' if item['all_graphic_compartments_meet_symbol_test'] else 'NO',
                             '',item['classification']])
    with (dest/'alpha20_tr_simboli_vettoriali.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        writer=csv.writer(fh,delimiter=';')
        writer.writerow(['pagina','simboli_circolari','coppie_avvolgimenti','candidati_asse_ingresso',
                         'stato','TR_padre_verificato'])
        for record in report.get('transformer_winding_geometry_evidence',[]):
            hyp=record['local_upstream_winding_hypotheses']
            writer.writerow([record['page'],record['circle_shapes_detected'],
                             record['winding_pairs_detected'],len(hyp['candidates']),hyp['status'],''])
    with (dest/'alpha20_qps_documentali.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        writer=csv.writer(fh,delimiter=';')
        writer.writerow(['campo_grafico','etichette_QPS_OCR','quadri_DC_grafici','QPS_documentati',
                         'sequenza_completa','stato','string_box_SAP'])
        for row in report.get('local_ocr_qps_evidence',{}).get('field_sequences',[]):
            writer.writerow([row['field_candidate'],row['ocr_qps_identifiers'],
                             row['graphic_dc_cabinets'],row['qps_documented_count'] or '',
                             'SI' if row['sequence_complete'] else 'NO',row['source'],''])
    for p,image in previews:
        canvas=image.copy();draw=ImageDraw.Draw(canvas)
        try:font=ImageFont.load_default(size=17)
        except TypeError:font=ImageFont.load_default()
        for row in report['input_conductor_runs']:
            if row['page']!=p:continue
            for a,b in row['evidence_segments_px']:
                draw.line((*[2*x for x in a],*[2*x for x in b]),fill='#1859bb',width=5)
            if row['upstream_terminal_px'] is not None:
                x,y=[2*v for v in row['upstream_terminal_px']]
                draw.ellipse((x-7,y-7,x+7,y+7),outline='#175abc',width=4)
                draw.text((x+10,y-17),'MORSETTO?',fill='#175abc',font=font)
        draw.text((10,8),'ALPHA20: tratti di conduttore solidi; TR NON CONFERMATO',fill='#175abc',font=font)
        canvas.save(dest/f'alpha20_tracce_ingresso_p{p}.png')
        cabinets=image.copy()
        brush=ImageDraw.Draw(cabinets)
        for item in report.get('dc_combiner_graphic_evidence',[]):
            if item['page']!=p:continue
            for cell in item['candidate_cabinet_evidence']:
                x1,y1,x2,y2=cell['bbox_px']
                brush.rectangle((2*x1,2*y1,2*x2,2*y2),outline='#853caa',width=3)
            boxes=item.get('candidate_cabinet_evidence',[])
            if boxes:
                b=boxes[0]['bbox_px']
                brush.text((2*b[0],max(12,2*b[1]-25)),
                           f"CAMPO {item['field_candidate']}: {len(boxes)} DC?",fill='#70328f',font=font)
        brush.text((10,8),'ALPHA20: CABINET DC? NON String Box confermate',fill='#70328f',font=font)
        cabinets.save(dest/f'alpha20_cabinet_dc_p{p}.png')
    return dest
