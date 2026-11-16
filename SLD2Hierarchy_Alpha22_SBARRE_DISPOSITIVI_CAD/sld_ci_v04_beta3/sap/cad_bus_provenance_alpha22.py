"""Alpha22: find drawn upstream busbars, explicitly recording unresolved device gaps.

Unlike assigning the nearest transformer, this module requires *source vector*
segments for the busbar, converter lead wires and the upstream transformer
secondary conductor. It never bridges a circuit breaker, insulator, switch,
transformer or unlabelled gap. Reported ancestry is a DOCUMENTARY CANDIDATE,
not automatically verified electrical connectivity or SAP parentage.

The algorithm is geometry based, accepts variable inverter fanouts, and never
reads filenames, labels, plant inventory, expected values or ground truth.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from PIL import Image, ImageDraw, ImageFont
from .cad_conductor_graph_alpha20 import extract_solid_conductors, frame_scale, _distance
from .vector_diagnostics_alpha17 import _render
from .cad_thresholds import CadBusThresholds, DEFAULT as DEFAULT_THRESHOLDS
from .cad_device_edges import collect_vertical_strokes, device_edges, tr_inverter_paths

SCHEMA='sld-alpha22-cad-bus-evidence/v1'


def _number(n):
    return type(n) in (int,float) and math.isfinite(n)


def _anchor(run):
    if not isinstance(run,dict) or run.get('status')!='SOLID_CONDUCTOR_TO_OPEN_UPSTREAM_TERMINAL':
        return None
    p=run.get('upstream_terminal_px')
    if not isinstance(p,(tuple,list)) or len(p)!=2 or not all(_number(v) for v in p):
        return None
    return (float(p[0]),float(p[1]))


def identify_common_buses(strokes, runs, *, page=1, max_gap=19.0, min_span=10.0,
                          transverse_tolerance=2.8, ambiguous_ratio=0.92):
    """Identify only a unique black horizontal source segment supporting >=2 leads.

    Upstream open terminals must be within a small bounded vertical distance
    of the bus. The gap is *NOT* bridged. The return includes all competing
    buses and leaves ambiguity visible instead of picking the closest stroke.
    """
    page_runs=[r for r in runs if r.get('page')==page]
    # Malformed upstream coordinates must not silently disappear from the
    # denominator of a supposedly complete source-backed bus.
    if any(_anchor(r) is None for r in page_runs):
        return {'status':'INVALID_OR_UNTRACED_PAGE_INPUT', 'bus':None,
                'candidate_buses':[], 'lead_count':len(page_runs), 'electrical_path_verified':False}
    runs=page_runs
    if len(runs)<2:
        return {'status':'INSUFFICIENT_TRACED_CONVERTER_INPUTS', 'bus':None,
                'candidate_buses':[], 'lead_count':len(runs), 'electrical_path_verified':False}
    # Indexed by line, not by plant-specific inverter numbering.
    choices=[]
    for i,stroke in enumerate(strokes):
        if len(stroke)!=2 or any(not all(_number(x) for x in endpoint) for endpoint in stroke):
            continue
        a,b=stroke
        if abs(a[1]-b[1])>.36:continue
        xmin,xmax=sorted((a[0],b[0])); length=xmax-xmin
        if length<min_span:continue
        yy=(a[1]+b[1])/2
        aligned=[]
        for run in runs:
            x,y=_anchor(run)
            vertical_distance=y-yy
            if -0.5<=vertical_distance<=max_gap and xmin-transverse_tolerance<=x<=xmax+transverse_tolerance:
                aligned.append({'converter_candidate_id':run['converter_candidate_id'],
                                'upstream_open_terminal_px':[round(x,3),round(y,3)],
                                'distance_bus_to_open_terminal_px':round(vertical_distance,3),
                                'gap_unbridged':vertical_distance>.5,
                                'source_input_run_status':run['status']})
        if len(aligned)<2:continue
        xs=[_anchor(run)[0] for run in runs]
        # A trustworthy common bus should extend across the lead group.
        cover=(min(xs)>=xmin-transverse_tolerance and max(xs)<=xmax+transverse_tolerance)
        score=(len(aligned)/len(runs), bool(cover), -sum(x['distance_bus_to_open_terminal_px'] for x in aligned)/len(aligned))
        choices.append({'source_stroke_index':i, 'bbox_px':[round(xmin,3),round(yy,3),round(xmax,3),round(yy,3)],
                        'source_length_px':round(length,3), 'members':aligned, 'covers_all_inputs':cover,
                        'members_count':len(aligned),'score':score})
    # Require a bus actually spanning the full range, not just a line near two
    # of three inputs. For partial coverage prefer to abstain.
    full=[x for x in choices if x['covers_all_inputs'] and x['members_count']==len(runs)]
    full.sort(key=lambda x:x['score'],reverse=True)
    compact=[{k:v for k,v in cand.items() if k!='score'} for cand in choices]
    if not full:
        return {'status':'NO_UNIQUE_FULL_SPAN_SOURCE_BUSBAR','bus':None,
                'candidate_buses':compact,'lead_count':len(runs),'electrical_path_verified':False}
    selected=full[0]
    if len(full)>1:
        # Two plausible horizontal lines at very similar distance to the
        # terminals are structurally ambiguous. Never silently choose one.
        if (abs(selected['score'][2]-full[1]['score'][2])<=max_gap*(1-ambiguous_ratio)):
            return {'status':'AMBIGUOUS_PARALLEL_BUSBARS','bus':None,
                    'candidate_buses':compact,'lead_count':len(runs),'electrical_path_verified':False}
    return {'status':'ONE_SOURCE_BUSBAR_WITH_UNBRIDGED_DEVICE_GAPS',
            'bus':{k:v for k,v in selected.items() if k!='score'},
            'candidate_buses':compact,'lead_count':len(runs),
            'electrical_path_verified':False}


def match_winding_to_bus(winding_evidence,bus,strokes,*,max_axis_offset=2.5,max_wire_gap=19.0):
    """Find one winding pair and a real downstream wire ending above the bus.

    Requiring the wire to be a source stroke that starts close to the winding
    excludes an assignment based only on visual proximity of a transformer.
    """
    if bus is None:
        return {'status':'NO_UNIQUE_BUS_FOR_WINDING','transformer':None,
                'electrical_path_verified':False}
    x0,by,x1,_=bus['bbox_px']; center=(x0+x1)/2
    candidates=[]
    for record in winding_evidence:
        h=record.get('local_upstream_winding_hypotheses') or {}
        for pair in h.get('candidates',[]):
            pair_x,pair_y=pair.get('center_px',[None,None])
            if not (_number(pair_x) and _number(pair_y)):continue
            if not x0-max_axis_offset<=pair_x<=x1+max_axis_offset:continue
            if by-pair_y<=3 or by-pair_y>150:continue
            matching=[]
            for i,(a,b) in enumerate(strokes):
                if abs(a[0]-b[0])>0.36:continue
                x=(a[0]+b[0])/2
                if abs(x-pair_x)>max_axis_offset:continue
                top,bottom=sorted((a[1],b[1]))
                if not (0<=top-pair_y<=24 and 0<by-bottom<=max_wire_gap):continue
                if bottom-top<4:continue
                matching.append((i,top,bottom,x))
            if matching:
                # Don't turn multiple conductor candidates into a verified
                # single path. Expose all their geometric source ids.
                best=max(matching,key=lambda m:m[2]-m[1])
                candidates.append({'winding_pair_source_paths':pair.get('source_path_indices'),
                                   'winding_pair_center_px':[pair_x,pair_y],
                                   'secondary_source_stroke_index':best[0],
                                   'secondary_source_stroke_bbox_px':[round(best[3],3),round(best[1],3),round(best[3],3),round(best[2],3)],
                                   'secondary_wire_to_bus_gap_px':round(by-best[2],3),
                                   'classification':'WINDING_PAIR_PLUS_SECONDARY_SOURCE_WIRE_WITH_DEVICE_GAP'})
    if not candidates:return {'status':'NO_WINDING_WITH_SOURCE_WIRE_NEAR_BUS',
                               'transformer':None,'electrical_path_verified':False}
    if len(candidates)!=1:return {'status':'AMBIGUOUS_MULTIPLE_WINDINGS_AT_BUS',
                                  'transformer':None,'candidates':candidates,'electrical_path_verified':False}
    return {'status':'ONE_WINDING_PAIR_AND_SECONDARY_WIRE_WITH_UNBRIDGED_GAP',
            'transformer':candidates[0],'electrical_path_verified':False}


def audit_bus_and_winding(strokes,runs,winding_evidence,*,page=1,thresholds:CadBusThresholds=DEFAULT_THRESHOLDS):
    """Pure, deterministic graph audit; no access to filenames or inventory."""
    t=thresholds
    buses=identify_common_buses(strokes,runs,page=page,max_gap=t.bus_max_gap,min_span=t.bus_min_span,
                                transverse_tolerance=t.bus_transverse_tolerance,
                                ambiguous_ratio=t.bus_ambiguous_ratio)
    winding=match_winding_to_bus(winding_evidence,buses.get('bus'),strokes,
                                 max_axis_offset=t.winding_max_axis_offset,
                                 max_wire_gap=t.winding_max_wire_gap)
    verified=[]
    if buses['bus']:
        verified=[r['converter_candidate_id'] for r in buses['bus']['members']]
    return {'page':page,'busbar_evidence':buses,'winding_evidence':winding,
            'converter_with_source_lead_and_bus_candidate':verified,
            'transformer_parentage_claimed':False,
            'structural_evidence_status':'VECTOR_BUS_AND_TR_WIRE_WITH_UNVERIFIED_INTERRUPTING_DEVICES'
              if buses['bus'] and winding.get('transformer') else 'PARTIAL_OR_AMBIGUOUS_VECTOR_EVIDENCE',
            'tr_inverter_automatically_verified':0,
            'bridges_through_switches_or_transformer_created':0,
            'source_ground_truth_used':False}



def open_gaps(audit_record):
    """Discontinuita verticali non attraversate: (tipo, entita_a_valle, x, y_monte, y_valle).

    - TR_SECONDARY_TO_BUSBAR: dal capo del filo secondario del TR alla sbarra;
    - BUSBAR_TO_INVERTER: dalla sbarra al morsetto aperto di ciascun inverter.
    """
    bus=audit_record['busbar_evidence'].get('bus')
    if not bus:return []
    _,by,_,_=bus['bbox_px']
    tr=audit_record['winding_evidence'].get('transformer')
    gaps=[]
    if tr:
        wire=tr['secondary_source_stroke_bbox_px']
        gaps.append(('TR_SECONDARY_TO_BUSBAR','TR_WINDING_CANDIDATE',wire[0],wire[3],by))
    for branch in bus['members']:
        x,cy=branch['upstream_open_terminal_px']
        gaps.append(('BUSBAR_TO_INVERTER',branch['converter_candidate_id'],x,by,cy))
    return gaps


def detect_series_apparatus_motifs(page, audit_record, thresholds:CadBusThresholds=DEFAULT_THRESHOLDS):
    """Identify source green/magenta in-line symbol motifs *inside* open gaps.

    This is deliberately a *device-like visual* class. It is NOT sufficient
    to classify an IOCB, switch, CT or other specific apparatus, and does not
    make any electrical connection. It gives the next semantic recognition
    stage explicit source path IDs and small bounding boxes to review.
    """
    gaps=open_gaps(audit_record)
    if not gaps:return []

    # Positions follow the page's rotated (display) coordinate frame, same as
    # Alpha20; no template, plant-name or expected fanout is supplied.
    # Stessa scala di extract_solid_conductors: sulle pagine < 1000 pt il
    # fattore e 1 (prima era 1000/lato, con coordinate sfalsate rispetto ai gap).
    k=frame_scale(page)
    rotation=page.rotation_matrix
    # "green" = contorno del simbolo, "magenta" = contatti interni (colori del profilo).
    outline_color=tuple(thresholds.series_outline_color)
    contact_color=tuple(thresholds.series_contact_color)
    green=[];magenta=[]
    for path_id,path in enumerate(page.get_drawings()):
        color=path.get('color')
        color=tuple(color) if color is not None else None
        if color not in (outline_color,contact_color):continue
        b=path['rect']*rotation
        a=tuple(float(v*k) for v in (b.x0,b.y0,b.x1,b.y1))
        if any(not math.isfinite(v) for v in a):continue
        if color==outline_color:
            w=a[2]-a[0];h=a[3]-a[1]
            if not (.8<=w<=5 and 1.5<=h<=7):continue
            if not (.25<=w/h<=1.8):continue
            green.append((path_id,a))
        else:magenta.append((path_id,a))
    matches=[];taken=[]
    for kind,subject,xx,y0,y1 in gaps:
        if y1<=y0:continue
        options=[]
        for idx,b in green:
            midx=(b[0]+b[2])/2;midy=(b[1]+b[3])/2
            if abs(midx-xx)>2.5 or midy<=y0+.3 or midy>=y1-.3:continue
            interior=[j for j,t in magenta if t[0]>=b[0]-.55 and t[2]<=b[2]+.55
                      and t[1]>=b[1]-.6 and t[3]<=b[3]+.6]
            if len(set(interior))<2:continue
            options.append((idx,b,sorted(set(interior))))
        # The source outline often consists of multiple nearby green paths.
        # Choose one *unique spatial box*, never one of two different devices.
        uniq=[]
        for o in sorted(options,key=lambda x:(-(x[1][2]-x[1][0])*(x[1][3]-x[1][1]),x[0])):
            # CAD exporters often split one green outline into a full
            # rectangle and smaller *contained* subpaths. They are not two
            # different devices. Separate disjoint rectangles remain ambiguous.
            def same_symbol(a,c):
                ax0,ay0,ax1,ay1=a;cx0,cy0,cx1,cy1=c
                eps=.24
                nested=(ax0-eps<=cx0 and ay0-eps<=cy0 and ax1+eps>=cx1 and ay1+eps>=cy1) or (
                        cx0-eps<=ax0 and cy0-eps<=ay0 and cx1+eps>=ax1 and cy1+eps>=ay1)
                near=(abs((ax0+ax1)-(cx0+cx1))<1.0 and abs((ay0+ay1)-(cy0+cy1))<1.0)
                return nested or near
            if not any(same_symbol(o[1],q[1]) for q in uniq):
                uniq.append(o)
        if len(uniq)==1:
            idx,b,contact=uniq[0]
            if idx not in taken:
                taken.append(idx)
                matches.append({'gap_type':kind,'downstream_entity':subject,
                                'outline_source_path_index':idx,
                                'contact_source_path_indices':contact,
                                'symbol_bbox_px':[round(v,3) for v in b],
                                'status':'IN_LINE_DEVICE_LIKE_SYMBOL_SOURCE_OBSERVED_UNCLASSIFIED',
                                'device_type_classified':False,
                                'device_edge_created':False})
        elif len(uniq)>1:
            matches.append({'gap_type':kind,'downstream_entity':subject,
                            'status':'AMBIGUOUS_MULTIPLE_SYMBOLS_IN_GAP',
                            'candidate_outlines':[o[0] for o in uniq],
                            'device_type_classified':False,'device_edge_created':False})
    return matches


def audit_cad_pdf(pdf_path,alpha20_report,thresholds:CadBusThresholds=DEFAULT_THRESHOLDS):
    """Run once per page with source transformer/converter evidence from Alpha20."""
    path=Path(pdf_path)
    dig=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            dig.update(block)
    h=dig.hexdigest()
    by_page=defaultdict(list)
    for run in alpha20_report.get('input_conductor_runs',[]):
        by_page[int(run['page'])].append(run)
    winding_page={int(w['page']):[w] for w in alpha20_report.get('transformer_winding_geometry_evidence',[])}
    output=[]
    with fitz.open(str(pdf_path)) as pdf:
        for pageno in sorted(by_page):
            if not 1<=pageno<=len(pdf):continue
            strokes=extract_solid_conductors(pdf[pageno-1])
            record=audit_bus_and_winding(strokes,by_page[pageno],winding_page.get(pageno,[]),
                                         page=pageno,thresholds=thresholds)
            record['source_series_device_visual_motifs']=detect_series_apparatus_motifs(
                pdf[pageno-1],record,thresholds)
            # Archi-dispositivo solo dove tratti disegnati coprono i gap (vedi cad_device_edges).
            edges=device_edges(collect_vertical_strokes(pdf[pageno-1]),open_gaps(record),
                               record['source_series_device_visual_motifs'],thresholds)
            record['device_edges']=edges
            record['device_edges_automatically_created']=sum(e['device_edge_created'] for e in edges)
            record['tr_inverter_paths_through_devices']=tr_inverter_paths(record,edges)
            output.append(record)
    return {'schema':SCHEMA,'source_pdf':str(path),'source_pdf_sha256':h,
            'thresholds':thresholds.as_dict(),
            'source_ground_truth_used':False,
            'text_inference_from_plant_filename':False,'electrical_continuity_not_inferred_across_gaps':True,
            'gaps_crossed_only_with_drawn_leads':True,
            'pages':output,
            'summary':{'pages_examined':len(output),
                       'page_bus_candidates_source_supported':sum(bool(x['busbar_evidence']['bus']) for x in output),
                       'converter_leads_aligned_to_common_bus':sum(len(x['converter_with_source_lead_and_bus_candidate']) for x in output),
                       'page_windings_with_source_secondary_wire':sum(bool(x['winding_evidence'].get('transformer')) for x in output),
                       'source_inline_device_like_motifs_unclassified':sum(
                           r.get('status')=='IN_LINE_DEVICE_LIKE_SYMBOL_SOURCE_OBSERVED_UNCLASSIFIED'
                           for p in output for r in p.get('source_series_device_visual_motifs',[])),
                       'device_edges_source_connected':sum(x['device_edges_automatically_created'] for x in output),
                       'tr_inverter_paths_through_unclassified_devices':sum(
                           len(x['tr_inverter_paths_through_devices']) for x in output),
                       'tr_inverter_automatically_electrically_verified':0,
                       'matrix_flow_import_ready':False}}


def write_alpha22_reports(pdf_path,report,out_dir):
    dest=Path(out_dir);dest.mkdir(parents=True,exist_ok=True)
    out_json=dest/'alpha22_audit_sbarre_e_discontinuita.json'
    out_csv=dest/'alpha22_relazioni_candidati.csv'
    out_json.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    with out_csv.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['pagina','inverter_grafico','sbarra_segmento_sorgente','sbarra_X0_Y_X1',
                    'coppia_avvolgimenti_tr_sorgente','filo_secondario_tr_sorgente',
                    'discontinuita_protezione','stato_parent','continuita_elettrica_automatica'])
        for page in report['pages']:
            b=page['busbar_evidence'].get('bus');tr=page['winding_evidence'].get('transformer')
            with_path={p['converter_candidate_id'] for p in page.get('tr_inverter_paths_through_devices',[])}
            for item in b.get('members',[]) if b else []:
                crossed=item['converter_candidate_id'] in with_path
                w.writerow([page['page'],item['converter_candidate_id'],b['source_stroke_index'],
                            json.dumps(b['bbox_px']),
                            json.dumps(tr['winding_pair_source_paths']) if tr else '',
                            tr['secondary_source_stroke_index'] if tr else '',
                            'ATTRAVERSATE_CON_ARCHI_DISPOSITIVO' if crossed else 'NON_PONTICELLATE',
                            'CANDIDATO_PERCORSO_CON_DISPOSITIVI_NON_CLASSIFICATI' if crossed
                            else 'CANDIDATO_GEOMETRICO_NON_CONFERMATO',
                            'NO'])
    out_devices=dest/'alpha22_dispositivi_in_serie_candidati.csv'
    with out_devices.open('w',newline='',encoding='utf-8-sig') as fh:
        w=csv.writer(fh,delimiter=';')
        w.writerow(['pagina','tipo_interruzione','apparecchiatura_a_valle','percorso_sorgente','contatti_sorgente',
                    'bbox_px','stato_simbolo','tipologia_elettrica_verificata','arco_dispositivo_creato'])
        for page in report['pages']:
            edge_ok={(e['gap_type'],e['downstream_entity']) for e in page.get('device_edges',[])
                     if e['device_edge_created']}
            for item in page.get('source_series_device_visual_motifs',[]):
                created=(item['gap_type'],item['downstream_entity']) in edge_ok
                w.writerow([page['page'],item['gap_type'],item['downstream_entity'],
                            item.get('outline_source_path_index',''),
                            json.dumps(item.get('contact_source_path_indices',[])),
                            json.dumps(item.get('symbol_bbox_px',[])),item['status'],'NO',
                            'SI' if created else 'NO'])
    result={'report':out_json,'csv':out_csv,'dispositivi':out_devices}
    checks=report.get('operator_review_cross_check') or []
    if checks:
        out_checks=dest/'alpha22_confronto_review_percorsi.csv'
        with out_checks.open('w',newline='',encoding='utf-8-sig') as fh:
            w=csv.writer(fh,delimiter=';')
            w.writerow(['gruppo_QPS','CU','TR','INV','inverter_grafico','avvolgimento_automatico','esito'])
            for c in checks:
                w.writerow([c['qps_group'],c['CU'],c['TR'],c['INV'],c['converter_candidate_id'] or '',
                            json.dumps(c['automatic_winding']) if c['automatic_winding'] else '',c['status']])
        result['confronto_review']=out_checks
    previews=[]
    # This is an optional visualization; failure does not alter provenance.
    try:
        with fitz.open(str(pdf_path)) as pdf:
            for r in report['pages']:
                b=r['busbar_evidence'].get('bus')
                if not b:continue
                page=pdf[r['page']-1]
                im=_render(page)
                # _render usa lo stesso rapporto di frame_scale: 1 px immagine = 1 unita di coordinata.
                k=1.0
                draw=ImageDraw.Draw(im)
                x0,y,x1,_=b['bbox_px']
                draw.line((x0*k,y*k,x1*k,y*k),fill='#e11d48',width=6)
                for member in b['members']:
                    xx,yy=member['upstream_open_terminal_px']
                    draw.ellipse((xx*k-7,yy*k-7,xx*k+7,yy*k+7),outline='#d97706',width=4)
                    draw.line((xx*k,y*k,xx*k,yy*k),fill='#d97706',width=3)
                tr=r['winding_evidence'].get('transformer')
                if tr:
                    xx,yy=tr['winding_pair_center_px']
                    draw.ellipse((xx*k-12,yy*k-12,xx*k+12,yy*k+12),outline='#2563eb',width=5)
                    wx0,wy0,wx1,wy1=tr['secondary_source_stroke_bbox_px']
                    draw.line((wx0*k,wy0*k,wx1*k,wy1*k),fill='#2563eb',width=4)
                for motif in r.get('source_series_device_visual_motifs',[]):
                    bb=motif.get('symbol_bbox_px')
                    if not bb:continue
                    draw.rectangle(((bb[0]-2)*k,(bb[1]-2)*k,(bb[2]+2)*k,(bb[3]+2)*k),
                                   outline='#7c3aed',width=3)
                draw.text((max(4,x0*k-70),max(4,y*k-100)),
                          'TR candidato | GAP non verificati | simboli viola candidati',
                          fill='#b45309',stroke_width=1,stroke_fill='white')
                name=dest/f'alpha22_evidenze_sbarra_p{r["page"]}.png'
                im.save(name);previews.append(str(name))
                # The full SLD is often an A0/A1 sheet. Provide a magnified
                # evidence view so an operator can inspect the actual gaps.
                cx0=max(0,(x0-125)*k);cx1=min(im.width,(x1+125)*k)
                cy0=max(0,(tr['winding_pair_center_px'][1]-35)*k if tr else (y-70)*k)
                cy1=min(im.height,(max((m['upstream_open_terminal_px'][1] for m in b['members']),
                                         default=y)+105)*k)
                if cx1-cx0>80 and cy1-cy0>80:
                    crop=im.crop((round(cx0),round(cy0),round(cx1),round(cy1)))
                    if crop.width<1600:
                        z= min(3,1600/crop.width)
                        crop=crop.resize((round(crop.width*z),round(crop.height*z)), Image.Resampling.LANCZOS)
                    detail=dest/f'alpha22_zoom_sbarra_p{r["page"]}.png'
                    crop.save(detail);previews.append(str(detail))
    except (ValueError,RuntimeError,OSError):
        pass
    return {**result,'previews':previews}
