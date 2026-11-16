"""Alpha21: source-bound QPS -> String Box and operator-scoped CAD hierarchy.

The SLD is parsed FIRST: OCR + DC cabinet geometry + converter/field correlation.
No counts are read from ground truth or operator review. The optional operator
review asserts only semantic meaning (QPS = String Box), QPS numbering semantics,
and the CU/TR/INV parentage for separately named inverter groups. An unsupported
review is rejected, never used to invent source assets or quantities.

In particular, 'QPS-2-4/8' is the fourth of eight QPS belonging to inverter
number two *only when a reviewed numbering convention supports that meaning*.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from collections import defaultdict

from .stereotypes_alpha12 import build_stereotype_export, write_stereotype_outputs

REVIEW_SCHEMA='sld-alpha21-cad-operator-topology/v1'
RESULT_SCHEMA='sld-alpha21-qps-source-evidence/v1'


def source_sha256(pdf_path):
    h=hashlib.sha256()
    with Path(pdf_path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def verified_qps_sequences(alpha20_report, alpha19_report):
    """Correlate only complete, unique source QPS sequences to graphic fields and converters.

    Does not declare these tokens SAP String Boxes or electrical parentage.
    Abstains if rank/position correlation is incomplete or source labels conflict.
    """
    fields=alpha20_report.get('local_ocr_qps_evidence',{}).get('field_sequences',[])
    graphic=alpha20_report.get('dc_combiner_graphic_evidence',[])
    candidate_by_field={(r['page'],r['field_candidate']):r for r in graphic}
    pairs=alpha19_report.get('candidate_graphic_correlations',[])
    pair_by_field=defaultdict(list)
    for p in pairs:
        if p.get('field_candidate') is not None:
            pair_by_field[(p['page'],p['field_candidate'])].append(p)
    rows=[];groups_seen=set(); converter_seen=set()
    for field in fields:
        toks=field.get('ocr_tokens',[])
        ids={t.get('group_on_drawing') for t in toks}
        k=(1,field['field_candidate'])  # alpha20 OCR currently reads page 1 only
        graphic_row=candidate_by_field.get(k)
        matching=pair_by_field.get(k,[])
        reasons=[]
        if not field.get('sequence_complete'):reasons.append('QPS_SEQUENCE_NOT_COMPLETE')
        if len(ids)!=1 or not toks:reasons.append('QPS_GROUP_ID_AMBIGUOUS')
        if not graphic_row or not graphic_row.get('all_graphic_compartments_meet_symbol_test'):
            reasons.append('DC_CABINET_GEOMETRY_NOT_COMPLETE')
        if len(matching)!=1 or matching[0].get('proposed_relation_status')!='CORRISPONDENZA_GRAFICA_ORDINALE_NON_VERIFICATA':
            reasons.append('CONVERTER_FIELD_CORRELATION_UNRESOLVED')
        group=next(iter(ids)) if len(ids)==1 else None
        quantity=field.get('qps_documented_count')
        if not isinstance(quantity,int) or isinstance(quantity,bool) or quantity<=0:
            reasons.append('QPS_QUANTITY_NOT_SUPPORTED')
        if group is not None:
            label=(1,group)
            if label in groups_seen:reasons.append('DUPLICATE_QPS_GROUP')
            groups_seen.add(label)
        converter=matching[0]['converter_candidate_id'] if len(matching)==1 else None
        if converter is not None:
            if converter in converter_seen: reasons.append('DUPLICATE_CONVERTER_FIELD_OWNER')
            converter_seen.add(converter)
        # The OCR group index must agree with the order of the correlated
        # converter only when the operator confirms the numbered convention;
        # otherwise preserve candidate identity independently of the label.
        rows.append({'page':1,'qps_group':group,'field_candidate':field['field_candidate'],
                     'converter_candidate_id':converter,'qps_documented':quantity if not reasons else None,
                     'sequence_complete':not reasons,
                     'evidence':'OCR_QPS_ORDINALS_PLUS_INDEPENDENT_CAD_DC_GEOMETRY',
                     'qps_labels':[t.get('normalized_designator','') for t in toks],
                     'qps_prefixes_exact':[bool(t.get('ocr_prefix_exact')) for t in toks],
                     'graphical_candidate_count':graphic_row.get('dc_combiner_like_cabinet_candidates') if graphic_row else None,
                     'unresolved_reasons':reasons,
                     'status':'QPS_DOCUMENTED_PARENT_UNVERIFIED' if not reasons else 'ABSTAIN_INCOMPLETE_SOURCE'})
    return rows


def validate_operator_review(review, pdf_path, plant_id, rows, converter_candidates):
    """Checks all asserted owners against PDF observations; never accepts counts from review."""
    if review is None:return None
    if not isinstance(review,dict) or review.get('schema')!=REVIEW_SCHEMA:
        raise ValueError('Schema review Alpha21 non valido')
    if review.get('plant_id') != plant_id:
        raise ValueError('Review relativa a un impianto differente')
    if review.get('source_pdf_sha256') != source_sha256(pdf_path):
        raise ValueError('Review relativa a una versione PDF differente')
    if review.get('qps_semantic_class')!='STRING_BOX' or review.get('qps_is_parallel_string_cabinet') is not True:
        raise ValueError('La review deve confermare QPS = Quadro Parallelo Stringhe / String Box')
    if review.get('qps_group_denotes_inverter_number') is not True:
        raise ValueError('Manca la conferma della convenzione numerica QPS-n-k/N')
    if review.get('operator_confirmed') is not True:
        raise ValueError('La review non contiene una conferma operatore esplicita')
    if not isinstance(review.get('operator_evidence'),str) or len(review['operator_evidence'].strip())<12:
        raise ValueError('Riferimento di verifica operatore insufficiente')
    assignments=review.get('parent_confirmations')
    if not isinstance(assignments,list) or not assignments:
        raise ValueError('Nessuna relazione CU/TR/inverter confermata')
    indexed={r['qps_group']:r for r in rows if r['sequence_complete'] and r['qps_group'] is not None}
    if len(indexed)!=len(rows) or len(indexed)!=len(converter_candidates):
        raise ValueError('Correlazioni documentali non complete: non applicare la review')
    matching={}; parent_keys=set(); referenced=set(); cu_trs=set()
    for a in assignments:
        if not isinstance(a,dict):raise ValueError('Riga review invalida')
        if any(type(a.get(k)) is not int or a[k]<1 for k in ('qps_group','CU','TR','INV')):
            raise ValueError('CU/TR/INV/gruppo devono essere interi positivi')
        g=a['qps_group']
        if g not in indexed or g in referenced:raise ValueError('Gruppo QPS assente, incompleto o ripetuto')
        if a['INV']!=g:
            raise ValueError('QPS-n-k/N identifica l inverter n nella convenzione confermata')
        if (a['CU'],a['TR'],a['INV']) in parent_keys:
            raise ValueError('Duplicazione parent CU/TR/INV')
        if indexed[g]['converter_candidate_id']!=f'INV_GRAFICO_{g:03d}':
            raise ValueError('Gruppo QPS non allineato al candidato inverter; revisione mirata necessaria')
        referenced.add(g);parent_keys.add((a['CU'],a['TR'],a['INV']));cu_trs.add((a['CU'],a['TR']))
        matching[g]=a
    if set(indexed)!=referenced:
        raise ValueError('Review parziale: in questa versione usare tutti i gruppi source-verificati')
    return matching


def build_alpha21_hierarchy(pdf_path, plant_id, alpha20_report, alpha19_report, converter_candidates, review=None):
    """Build safe QPS report + optional reviewed SAP staging Excel model."""
    if not plant_id.startswith('CI::'):raise ValueError('plant_id deve iniziare con CI::')
    sequences=verified_qps_sequences(alpha20_report,alpha19_report)
    assignments=validate_operator_review(review,pdf_path,plant_id,sequences,converter_candidates) if review else None
    for r in sequences:
        r['string_box_quantity']=r['qps_documented'] if assignments is not None and r['qps_group'] in assignments else None
        r['parent_status']='CONFERMATO_DA_OPERATORE_NON_VERIFICA_ELETTRICA' if assignments else 'NON_RISOLTO'
        r['semantic_status']='QPS_EQUIVALENTE_STRING_BOX_CONFERMATO_OPERATORE' if assignments else 'QPS_IDENTIFICATO_CLASSIFICAZIONE_SAP_NON_CONFERMATA'
    s={'converter_candidates':len(converter_candidates),
       'qps_groups_complete':sum(r['sequence_complete'] for r in sequences),
       'qps_documented_total':sum(r['qps_documented'] or 0 for r in sequences),
       'string_boxes_operator_semantics_resolved':sum(r['string_box_quantity'] or 0 for r in sequences),
       'tr_inverter_automatic_electrical_links_verified':0,
       'operator_confirmed_parent_links':len(assignments) if assignments else 0,
       'matrix_flow_import_ready':False,'ground_truth_used_for_inference':False}
    out={'schema':RESULT_SCHEMA,'plant_id':plant_id,'source_pdf':str(pdf_path),
         'source_pdf_sha256':source_sha256(pdf_path),'summary':s,'qps_sequences':sequences,
         'operator_review_applied':bool(assignments),
         'review_source':review['operator_evidence'] if review else None,
         'note':'La quantita deriva da etichette QPS rilevate in PDF e cabinet CAD. '
                'Il significato QPS=String Box, la numerazione e CU/TR sono confermati dall operatore, '
                'NON da continuita elettrica verificata automaticamente.'}
    if assignments is None:return out,None
    # The graph model comes solely from explicit operator confirmations.
    assets=[];cu_keys=sorted({a['CU'] for a in assignments.values()})
    for cu in cu_keys:assets.append({'asset_id':f'{plant_id}::CU::{cu:02d}',
                                    'type':'CONVERSION_UNIT','parent_id':plant_id,
                                    'source_status':'OPERATOR_CONFIRMED_NOT_AUTOMATIC_GRAPH'})
    for cu,tr in sorted({(a['CU'],a['TR']) for a in assignments.values()}):
        assets.append({'asset_id':f'{plant_id}::TR::{cu:02d}.{tr:02d}',
                       'type':'MV_LV_TRANSFORMER','parent_id':f'{plant_id}::CU::{cu:02d}',
                       'source_status':'OPERATOR_CONFIRMED_TR_IDENTITY'})
    for group in sorted(assignments):
        a=assignments[group];cu,tr,inv=(a[k] for k in ('CU','TR','INV'))
        inv_id=f'{plant_id}::INV::{cu:02d}.{inv:02d}'
        tr_id=f'{plant_id}::TR::{cu:02d}.{tr:02d}'
        source=next(x for x in sequences if x['qps_group']==group)
        evidence=f"{review['operator_evidence']} | CU{cu}:TR{tr}:INV{inv} | QPS-{group}-k/N PDF p1"
        assets.append({'asset_id':inv_id,'type':'CENTRAL_INVERTER','parent_id':tr_id,
                       'cu_context_id':f'{plant_id}::CU::{cu:02d}',
                       'source_status':'CAD_CANDIDATE_OPERATOR_CONFIRMED_IDENTITY',
                       'parentage':'OPERATOR_CONFIRMED_TR_PARENT',
                       'operator_evidence_ref':evidence})
        assets.append({'asset_id':f'{plant_id}::SB_QUANTITY::{cu:02d}.{inv:02d}',
                       'type':'STRING_BOX_QUANTITY','parent_id':inv_id,
                       'quantity':source['qps_documented'],
                       'evidence_ref':f"PDF:p1: {','.join(source['qps_labels'])} | geometric_DC_cabinets={source['graphical_candidate_count']} | semantic equivalence confirmed by operator"})
    baseline={'schema':'sld-sap-label-first-alpha10/v1','plant_id':plant_id,
              'source_pdf':str(pdf_path),'assets':assets}
    proposals={'schema':'sld-sap-alpha11-tr-inverter-proposals/v1','plant_id':plant_id,
               'source_pdf':str(pdf_path),'candidates':[]}
    export=build_stereotype_export(baseline,proposals)
    export['policy'] += ' Source QPS ordinal counts; semantic and parent scope from operator review. Not graph-verified.'
    for e in export['evidence']:
        e['stato_string_box']='CONTEGGIO_QPS_DA_OCR_GEOMETRIA_CON_SEMANTICA_HITL'
    export['summary']['tr_inverter_automatic_electrical_links_verified']=0
    export['summary']['semantic_equivalence_from_operator']=True
    export['review_source']=review['operator_evidence']
    return out,export


def write_alpha21_outputs(report,export,out_dir):
    dest=Path(out_dir);dest.mkdir(parents=True,exist_ok=True)
    (dest/'alpha21_diagnostica_qps.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (dest/'alpha21_qps_staging.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['pagina','gruppo_QPS','inverter_grafico','campo_grafico','QPS_documentati',
                    'String_Box_SAP','stato','origine','avvertenze'])
        for r in report['qps_sequences']:
            w.writerow([r['page'],r['qps_group'] or '',r['converter_candidate_id'] or '',r['field_candidate'],
                        r['qps_documented'] if r['qps_documented'] is not None else '',
                        r['string_box_quantity'] if r['string_box_quantity'] is not None else '',
                        r['semantic_status'],r['evidence'],','.join(r['unresolved_reasons'])])
    paths={'diagnostica':dest/'alpha21_diagnostica_qps.json','qps_staging':dest/'alpha21_qps_staging.csv'}
    if export:
        original=write_stereotype_outputs(export,dest)
        replacements={ 'csv':'alpha21_CU_TR_INV_STR_Box.csv',
                       'excel':'alpha21_gerarchie_stereotipi.xlsx',
                       'evidence_csv':'alpha21_evidenze.csv',
                       'json':'alpha21_riepilogo.json'}
        for key,new_name in replacements.items():
            source=original[key]; target=dest/new_name
            source.rename(target);paths[key]=target
    return paths
