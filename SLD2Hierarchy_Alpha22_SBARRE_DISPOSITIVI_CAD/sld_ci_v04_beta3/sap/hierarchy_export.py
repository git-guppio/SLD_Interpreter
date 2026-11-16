"""SAP PoC hierarchy staging, HITL queues and conservative cardinality gates.

Reads dev14c resolved identity/tree, unchanged. Operator confirmations are
explicit, scoped additions only: no assumption-based insertion, no arbitrary
transformer-to-inverter pairing, no feeder dependency and no implicit zero.
"""
from __future__ import annotations
import copy
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = "sld-sap-hierarchy-alpha9/v1"
REVIEW_SCHEMA = "sld-sap-operator-confirmations/v1"
# All these are the user-defined PoC target model, not universally valid plant laws.
TARGET_TYPES = {
    "CONVERSION_UNIT": (None, "conversion_unit"),
    "IOCB": ("CONVERSION_UNIT", "inverter_output_circuit_breaker"),
    "MV_LV_TRANSFORMER": ("CONVERSION_UNIT", "lv_mv_step_up_transformer"),
    "CENTRAL_INVERTER": ("CONVERSION_UNIT", "central_inverter"),
    "LV_LV_TRANSFORMER": ("CENTRAL_INVERTER", "lv_lv_field_transformer"),
    "STRING_BOX": ("CENTRAL_INVERTER", "string_box"),
}
MIN_CHILDREN = {
    "CONVERSION_UNIT": ("IOCB", "MV_LV_TRANSFORMER", "CENTRAL_INVERTER"),
    "CENTRAL_INVERTER": ("LV_LV_TRANSFORMER", "STRING_BOX"),
}


def _must_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: serve ID non vuoto")
    return value.strip()


def _source_base(source: dict[str, Any]) -> dict[str, Any]:
    if 'interpretation' not in source or 'plant' not in source:
        raise ValueError("Richiesto JSON completo dev14c_inference.json, non un report integrato sintetico")
    return source


def make_review_template(plant_id: str, tasks: list[dict]) -> dict:
    return {
        "schema": REVIEW_SCHEMA,
        "plant_id": plant_id,
        "instructions": "Inserire solo asset effettivamente verificati dall'operatore. Ogni asset necessita di ID univoco, tipo, parent_id e riferimento evidenza. Non compilare quantity=1 per presunzione.",
        "confirmed_assets": [],
        "confirmed_transformer_inverter_links": [],
        "outstanding_task_ids": [x['task_id'] for x in tasks],
    }


def build_sap_hierarchy(source: dict[str, Any], review: dict | None = None) -> dict[str, Any]:
    base = _source_base(source)
    plant_id = _must_id((base.get('plant') or {}).get('plant_id'), 'plant.plant_id')
    target = ((base.get('interpretation') or {}).get('target_hierarchy') or {})
    if not isinstance(target.get('nodes'), list):
        raise ValueError('target_hierarchy.nodes non disponibili nel JSON dev14c')
    expected = review or {}
    if review is not None:
        if expected.get('schema') != REVIEW_SCHEMA:
            raise ValueError('Schema di conferma operatore errato')
        if expected.get('plant_id') != plant_id:
            raise ValueError('Conferme appartenenti a un impianto diverso: operazione vietata')
    nodes: dict[str, dict] = {}
    for row in target['nodes']:
        kind = row.get('entity_type')
        if kind not in TARGET_TYPES:
            continue
        eid = _must_id(row.get('entity_id'), 'entity_id')
        if eid in nodes:
            raise ValueError(f'Identita duplicata nella baseline: {eid}')
        nodes[eid] = {
            'asset_id': eid, 'entity_type': kind,
            'parent_id': row.get('parent_id'),
            'source_status': row.get('source_status') or 'UNSPECIFIED',
            'evidence_basis': row.get('membership_basis') or 'DEV14C_RESOLVED_HIERARCHY',
            'evidence_ref': f'dev14c::target_hierarchy.nodes::{eid}',
            'operator_confirmed': False,
            'label': row.get('label') or row.get('tag') or '',
        }
    review_ids = set()
    for row in expected.get('confirmed_assets', []):
        if not isinstance(row, dict):
            raise ValueError('Una conferma asset non e un oggetto JSON')
        eid = _must_id(row.get('asset_id'), 'confirmed_assets.asset_id')
        if eid in nodes or eid in review_ids:
            raise ValueError(f'Asset gia presente o ripetuto, non duplicare: {eid}')
        review_ids.add(eid)
        kind = _must_id(row.get('entity_type'), 'confirmed_assets.entity_type')
        if kind not in TARGET_TYPES:
            raise ValueError(f'Tipo asset non ammesso per la PoC: {kind}')
        evidence = _must_id(row.get('evidence_ref'), 'confirmed_assets.evidence_ref')
        parent = row.get('parent_id')
        if parent is not None:
            parent = _must_id(parent, 'confirmed_assets.parent_id')
        nodes[eid] = {
            'asset_id':eid,'entity_type':kind,'parent_id':parent,
            'source_status':'OPERATOR_CONFIRMED', 'evidence_basis':'EXPLICIT_OPERATOR_CONFIRMATION',
            'evidence_ref':evidence, 'operator_confirmed':True,
            'label':str(row.get('label') or ''),
        }
    structural_errors = []
    for x in nodes.values():
        required_parent_type = TARGET_TYPES[x['entity_type']][0]
        if required_parent_type is None:
            if x['parent_id'] is not None:
                structural_errors.append({'asset_id':x['asset_id'],'reason':'CU_PARENT_MUST_BE_PLANT'})
            continue
        parent = nodes.get(x['parent_id'])
        if parent is None:
            structural_errors.append({'asset_id':x['asset_id'],'reason':'PARENT_MISSING_OR_UNRESOLVED','parent_id':x['parent_id']})
        elif parent['entity_type'] != required_parent_type:
            structural_errors.append({'asset_id':x['asset_id'],'reason':'WRONG_PARENT_TYPE',
                                      'required':required_parent_type,'actual':parent['entity_type']})
    # Invalid ancestry is not valid SAP membership. Propagate errors to descendants,
    # regardless of dictionary insertion order.
    invalid={x['asset_id'] for x in structural_errors}
    changed=True
    while changed:
        changed=False
        for eid,x in nodes.items():
            if eid not in invalid and x['parent_id'] in invalid:
                invalid.add(eid)
                structural_errors.append({'asset_id':eid,'reason':'PARENT_IS_INVALID'})
                changed=True
    valid=set(nodes)-invalid
    # A true count is reserved for identified and hierarchically resolved IDs.
    rows=[]
    for eid in sorted(valid):
        x=nodes[eid]
        if x['parent_id'] is not None and x['parent_id'] not in valid:
            continue
        rows.append({**x, 'sap_asset_type':TARGET_TYPES[x['entity_type']][1],
                     'hierarchy_level':1 if x['entity_type']=='CONVERSION_UNIT' else
                         3 if x['entity_type'] in ('LV_LV_TRANSFORMER','STRING_BOX') else 2,
                     'plant_id':plant_id})
    ids={r['asset_id'] for r in rows}
    by_parent: dict[str,Counter] = {}
    for r in rows:
        if r['parent_id'] in ids:
            by_parent.setdefault(r['parent_id'],Counter())[r['entity_type']]+=1
    tasks=[]
    def task(parent_id:str, kind:str, found:int,minimum:int=1):
        tasks.append({'task_id':f'{parent_id}::{kind}::MINIMUM',
                      'plant_id':plant_id, 'parent_id':parent_id,
                      'required_type':kind,'minimum_required':minimum,
                      'resolved_count':found,'shortfall_lower_bound':max(0,minimum-found),
                      'status':'REQUIRES_OPERATOR_REVIEW',
                      'reason':'MINIMUM_NOT_CONFIRMED; MISSING_IN_DOCUMENT_IS_NOT_ZERO_PHYSICAL_ASSETS'})
    plant_cus=[x for x in rows if x['entity_type']=='CONVERSION_UNIT']
    if not plant_cus:
        task(plant_id, 'CONVERSION_UNIT',0)
    for r in rows:
        for child_type in MIN_CHILDREN.get(r['entity_type'],()):
            count=by_parent.get(r['asset_id'],Counter())[child_type]
            if count < 1:
                task(r['asset_id'],child_type,count)
    for problem in structural_errors:
        tasks.append({'task_id':f"{problem['asset_id']}::INVALID_PARENT",'plant_id':plant_id,
                     'status':'REQUIRES_OPERATOR_REVIEW','reason':problem['reason'],
                     'asset_id':problem['asset_id'],'details':problem})
    # Baseline reports can include canonical CU identities only in layout that
    # cannot be safely given an entity ID here. Do not invent such entities.
    summary=base.get('target_counts') or {}
    canonical_total=summary.get('conversion_units')
    if isinstance(canonical_total,int) and canonical_total > len(plant_cus):
        tasks.append({'task_id':f'{plant_id}::CANONICAL_CUS_UNMAPPED', 'plant_id':plant_id,
                      'status':'REQUIRES_OPERATOR_REVIEW','reason':'CANONICAL_CU_IDENTITIES_NOT_MAPPED_TO_SAP_NODES',
                      'canonical_cu_count':canonical_total,'identified_cu_nodes':len(plant_cus)})
    for missing in target.get('unresolved_membership',[]) or []:
        tasks.append({'task_id':f"{missing.get('entity_id','UNKNOWN')}::UNRESOLVED_MEMBERSHIP",
                      'plant_id':plant_id, 'status':'REQUIRES_OPERATOR_REVIEW',
                      'reason':'UNRESOLVED_PARENT_IN_LEGACY', 'details':missing})
    src=base.get('sources') or {}
    source_complete=bool((src.get('sld') or {}).get('analysis_complete')) and (
        not (src.get('layout') or {}).get('present',False) or bool((src.get('layout') or {}).get('analysis_complete')))
    if not source_complete:
        tasks.append({'task_id':f'{plant_id}::SOURCE_PARTIAL','plant_id':plant_id,
                      'status':'REQUIRES_OPERATOR_REVIEW','reason':'PDF_SOURCE_ANALYSIS_NOT_COMPLETE'})
    # Only explicit operator-supplied links: a transformer with two secondary
    # outputs is still ONE asset. Linkage is useful but not a SAP parent change.
    associations=[];seen_links=set()
    for link in expected.get('confirmed_transformer_inverter_links',[]):
        tid=_must_id(link.get('transformer_id'),'transformer_id')
        iid=_must_id(link.get('inverter_id'),'inverter_id')
        evidence=_must_id(link.get('evidence_ref'),'link.evidence_ref')
        if tid not in ids or iid not in ids:
            raise ValueError('Associazione TR-inverter: identita inesistente o non risolta')
        if nodes[tid]['entity_type']!='MV_LV_TRANSFORMER' or nodes[iid]['entity_type']!='CENTRAL_INVERTER':
            raise ValueError('Associazione TR-inverter: tipi incompatibili')
        if nodes[tid]['parent_id'] != nodes[iid]['parent_id']:
            raise ValueError('Associazione TR-inverter tra CU differenti vietata')
        sec=link.get('secondary_index')
        if sec is not None and (type(sec) is not int or sec < 1):
            raise ValueError('secondary_index deve essere un intero positivo')
        if (tid,iid) in seen_links:
            raise ValueError('Associazione TR-inverter duplicata')
        seen_links.add((tid,iid))
        associations.append({'transformer_id':tid,'inverter_id':iid,'secondary_index':sec,
                             'evidence_ref':evidence,'confirmation':'OPERATOR_CONFIRMED'})
    if len({(x['transformer_id'],x['secondary_index']) for x in associations if x['secondary_index'] is not None}) < len([x for x in associations if x['secondary_index'] is not None]):
        raise ValueError('Secondario di trasformatore assegnato a due inverter diversi')
    counts=Counter(r['entity_type'] for r in rows)
    hitl_groups=[{'required_type':k,'task_count':v} for k,v in sorted(Counter(t.get('required_type','OTHER') for t in tasks).items())]
    return {
        'schema':SCHEMA,'plant_id':plant_id,
        'status':'HITL_REQUIRED' if tasks else 'HIERARCHY_STAGED_FOR_MATRIX_MAPPING',
        'matrix_flow_import_ready':False,
        'matrix_flow_schema_verified':False,
        'sap_functional_locations_generated':False,
        'feeder_required_for_sap':False,
        'ground_truth_used_to_modify_inference':False,
        'provenance_policy':'RESOLVED_IDENTITIES_PLUS_EXPLICIT_PLANT_SCOPED_OPERATOR_CONFIRMATIONS_ONLY',
        'plant_summary':{'identified_cu_count':counts['CONVERSION_UNIT'],
                         'counts_resolved_by_type':dict(counts),
                         'hitl_task_count':len(tasks),'source_analysis_complete':source_complete},
        'assets':rows,
        'transformer_inverter_associations':associations,
        'hitl_tasks':tasks, 'hitl_groups':hitl_groups,
        'baseline_structural_errors':structural_errors,
        'note':'CSV is a provisional normalized staging contract; actual Matrix Flow columns and SAP FL code generation require mapping confirmation.',
    }


def save_sap_outputs(result:dict, directory:str|Path) -> list[str]:
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    (out/'sap_hierarchy_alpha9.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    fields=['plant_id','asset_id','sap_asset_type','entity_type','parent_id','hierarchy_level',
            'label','source_status','evidence_basis','evidence_ref','operator_confirmed']
    with (out/'sap_hierarchy_alpha9.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=';');w.writeheader();w.writerows({k:x.get(k) for k in fields} for x in result['assets'])
    with (out/'sap_hitl_tasks_alpha9.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['task_id','plant_id','parent_id','required_type','minimum_required','resolved_count','reason','status']
        w=csv.DictWriter(f,fieldnames=fields,delimiter=';');w.writeheader();w.writerows({k:x.get(k) for k in fields} for x in result['hitl_tasks'])
    # Scope-specific resolved counts for Matrix Flow requirements gathering;
    # count 0 here means no resolved IDs in evidence, NOT physical absence.
    byparent={}
    for asset in result['assets']:
        byparent.setdefault(asset['parent_id'],Counter())[asset['entity_type']]+=1
    pending={}
    for t in result['hitl_tasks']:
        if t.get('required_type'):
            pending.setdefault(t['parent_id'],set()).add(t['required_type'])
    sc_fields=['plant_id','scope_type','scope_id','parent_id','iocb_resolved',
               'mv_lv_transformer_resolved','central_inverter_resolved',
               'lv_lv_transformer_resolved','string_box_resolved','pending_minimum_types']
    with (out/'sap_scope_counts_alpha9.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=sc_fields,delimiter=';');w.writeheader()
        for x in result['assets']:
            if x['entity_type'] not in ('CONVERSION_UNIT','CENTRAL_INVERTER'):
                continue
            c=byparent.get(x['asset_id'],Counter())
            w.writerow({'plant_id':result['plant_id'],'scope_type':x['entity_type'],
                        'scope_id':x['asset_id'],'parent_id':x['parent_id'],
                        'iocb_resolved':c['IOCB'],
                        'mv_lv_transformer_resolved':c['MV_LV_TRANSFORMER'],
                        'central_inverter_resolved':c['CENTRAL_INVERTER'],
                        'lv_lv_transformer_resolved':c['LV_LV_TRANSFORMER'],
                        'string_box_resolved':c['STRING_BOX'],
                        'pending_minimum_types':'|'.join(sorted(pending.get(x['asset_id'],set())))})
    with (out/'sap_hitl_groups_alpha9.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['required_type','task_count'],delimiter=';');w.writeheader()
        w.writerows(result['hitl_groups'])
    template=make_review_template(result['plant_id'],result['hitl_tasks'])
    (out/'sap_operator_review_TEMPLATE.json').write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding='utf-8')
    return [str(out/x) for x in ('sap_hierarchy_alpha9.json','sap_hierarchy_alpha9.csv',
        'sap_scope_counts_alpha9.csv','sap_hitl_tasks_alpha9.csv',
        'sap_hitl_groups_alpha9.csv','sap_operator_review_TEMPLATE.json')]
