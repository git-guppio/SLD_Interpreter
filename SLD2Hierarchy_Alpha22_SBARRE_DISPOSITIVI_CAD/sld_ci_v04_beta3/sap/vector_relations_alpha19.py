"""Alpha19: strict spatial correlation of *unverified* CAD graphic candidates.

This does NOT classify string boxes, transformers, electrical connectivity or SAP
assets. It makes each rank-order spatial hypothesis inspectable and refuses to
pair mismatched, overlapping, upward, non-coplanar, or singleton groups.

Ground truth TXT files, SLD filenames, inverter/TR cardinality constants and
manufacturer metadata are intentionally absent from this module.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path

from PIL import ImageDraw, ImageFont

from .vector_semantics_alpha18 import inspect_vector_semantics, write_semantics_outputs


def _center_x(b):
    return (float(b[0]) + float(b[2])) / 2.0


def _field_bounds(field):
    boxes = field.get('panel_boxes_px', [])
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def correlate_graphic_candidates(converters, fields):
    """Return proposals and abstentions; all statuses remain unverified.

    A single-page rank matching is permitted only where an unambiguous bijection
    exists in two non-overlapping ordered sequences and every field lies below
    the inverter-like graphic. This is *not* conductor tracing.
    """
    by_page_c = defaultdict(list)
    by_page_f = defaultdict(list)
    for c in converters:
        by_page_c[c['page']].append(c)
    for f in fields:
        by_page_f[f['page']].append(f)
    rows=[]
    page_diagnostics=[]
    for page in sorted(set(by_page_c) | set(by_page_f)):
        invs=sorted(by_page_c[page],key=lambda c:_center_x(c['bbox_px']))
        downstream=sorted(by_page_f[page],key=lambda f:_center_x(_field_bounds(f)) if _field_bounds(f) else float('inf'))
        reasons=[]
        if len(invs) < 2 or len(downstream) < 2:
            reasons.append('INSUFFICIENT_REPEATS')
        if len(invs) != len(downstream):
            reasons.append('CARDINALITY_MISMATCH')
        if any((a['bbox_px'][2] > b['bbox_px'][0]) for a,b in zip(invs,invs[1:])):
            reasons.append('OVERLAPPING_CONVERTERS')
        field_boxes=[_field_bounds(f) for f in downstream]
        if any(box is None for box in field_boxes):
            reasons.append('MISSING_FIELD_EVIDENCE')
        if field_boxes and all(field_boxes):
            if any(a[2] > b[0] for a,b in zip(field_boxes,field_boxes[1:])):
                reasons.append('OVERLAPPING_FIELDS')
            if invs and min(b[1] for b in field_boxes) <= max(c['bbox_px'][3] for c in invs):
                reasons.append('NON_DOWNSTREAM_PANEL')
        eligible=not reasons
        for i,c in enumerate(invs):
            field=downstream[i] if eligible else None
            note=([
                'ORDINE_SINISTRA_DESTRA_STESSA_PAGINA',
                'PANNELLI_A_VALLE_GEOMETRICAMENTE',
                'NESSUNA_TRACCIA_ELETTRICA_DIMOSTRATA',
            ] if field else [])
            equal=(field is not None and
                   c['outgoing_branches_observed']==field['compartments_observed'])
            if equal:note.append('RAMI_E_COMPARTIMENTI_NUMERICAMENTE_UGUALI_NON_PROVA_DI_CONNESSIONE')
            row={
                'page':page,
                'converter_candidate_id':c['candidate_id'],
                'converter_bbox_px':c['bbox_px'],
                'outgoing_branches_observed':c['outgoing_branches_observed'],
                'field_candidate':field['field_candidate'] if field else None,
                'field_panel_boxes_px':field['panel_boxes_px'] if field else [],
                'graphic_panels_observed':field['graphic_panels'] if field else None,
                'graphic_compartments_observed':field['compartments_observed'] if field else None,
                'branches_equal_compartments':equal if field else None,
                'proposed_relation_status': 'CORRISPONDENZA_GRAFICA_ORDINALE_NON_VERIFICATA' if field else 'NON_ASSOCIATO',
                'inferred_string_boxes':None,
                'tr_parent':None,
                'cu_parent':None,
                'electric_path_verified':False,
                'classification_evidence':note,
                'unresolved_reasons':reasons[:] if not field else ['SB_NON_CLASSIFICATE','TR_NON_RICONOSCIUTO'],
            }
            rows.append(row)
        page_diagnostics.append({'page':page,'converters':len(invs),
                                 'graphic_fields':len(downstream),
                                 'proposed_pairs':len(invs) if eligible else 0,
                                 'abstained':not eligible,
                                 'reasons':reasons})
    return rows,page_diagnostics


def inspect_cad_relations(pdf_path, max_pages=3):
    base,previews=inspect_vector_semantics(pdf_path,max_pages=max_pages)
    pairs,pages=correlate_graphic_candidates(base['converter_candidates'],
                                            base['downstream_field_candidates'])
    report={
        'schema':'sld-alpha19-vector-hypotheses/v1',
        'source_pdf':str(Path(pdf_path)),
        'alpha18_source_schema':base['schema'],
        'status':'GRAPHIC_HYPOTHESES_ONLY_NOT_SAP',
        'page_diagnostics':pages,
        'candidate_graphic_correlations':pairs,
        'summary':{'inverter_like_candidates':len(base['converter_candidates']),
                   'fields_detected':len(base['downstream_field_candidates']),
                   'non_electrical_spatial_proposals':sum(r['field_candidate'] is not None for r in pairs),
                   'verified_inverters':None,
                   'verified_tr_inverter_parents':0,
                   'verified_string_boxes':None,
                   'matrix_flow_import_ready':False},
        'ground_truth_used':False,
        'reference_txt_used':False,
        'note':'CORRISPONDENZA GRAFICA: non equivale a continuita elettrica. '
               '8 rami/8 compartimenti non implicano 8/16 String Box. '
               'I valori CU, TR e String Box rimangono da riconoscere.',
    }
    return base,previews,report


def write_cad_relation_outputs(base, previews, report, output):
    dest=write_semantics_outputs(base,previews,output)
    (dest/'alpha19_ipotesi_grafiche.json').write_text(
        json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    with (dest/'alpha19_correlazioni_grafiche.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['pagina','candidato_inverter','campo_grafico_ipotizzato',
                    'rami_uscita_osservati','pannelli_grafici','compartimenti_grafici',
                    'string_box_quantita','trasformatore_padre','CU_padre','stato','motivi'])
        for r in report['candidate_graphic_correlations']:
            w.writerow([r['page'],r['converter_candidate_id'],r['field_candidate'] or '',
                        r['outgoing_branches_observed'],r['graphic_panels_observed'] or '',
                        r['graphic_compartments_observed'] or '',
                        '', '', '',r['proposed_relation_status'],','.join(r['unresolved_reasons'])])
    for p,image in previews:
        canvas=image.copy()
        pen=ImageDraw.Draw(canvas)
        try:font=ImageFont.load_default(size=16)
        except TypeError:font=ImageFont.load_default()
        candidates=[r for r in report['candidate_graphic_correlations'] if r['page']==p]
        for row in candidates:
            if row['field_candidate'] is None:continue
            n=row['field_candidate']
            for box in row['field_panel_boxes_px']:
                b=tuple(2*int(z) for z in box)
                pen.rectangle(b,outline='#a33caf',width=5)
                pen.text((b[0]+4,b[1]+3),f'F?{n}',fill='#7b2e87',font=font)
            b=row['converter_bbox_px']
            pen.text((2*b[0], max(0,2*b[1]-48)),f'I?{n} / F?{n}',
                     fill='#9a2485',font=font)
        pen.text((10,6),'ALPHA19: ipotesi ordinali, NON collegamenti elettrici',
                 fill='#8a1470',font=font)
        canvas.save(dest/f'alpha19_anteprima_associazioni_p{p}.png')
    return dest
