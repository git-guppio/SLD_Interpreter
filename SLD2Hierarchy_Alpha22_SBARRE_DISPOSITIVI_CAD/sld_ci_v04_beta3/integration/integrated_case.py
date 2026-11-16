"""First end-to-end *integration* of dev14c document inference and beta3 geometry.

It runs the existing inference as-is, without reading regression oracles/ground
truth, then samples genuine FUSED named symbols on real SLD pages for independent
beta3 ROI path analysis. The source and new outputs are separate. No local
geometry result is promoted to electrical feeder membership.
"""
from __future__ import annotations

from collections import Counter,defaultdict
import json
from pathlib import Path
from typing import Any

from sld_ci_v04_beta2_dev14c.cli import run_case
from sld_ci_v04_beta2_dev14c.config import RunConfig
from sld_ci_v04_beta2_dev14c.source_resolution import validate_source_pair
from .auto_pair import plan_pairs, inspect_pair
from .identity_tasks import plan_cu_verifications, inspect_identity_neighborhoods
from .knowledge_scope import stage_knowledge
from .cross_sheet import analyze_cross_sheet

SCHEMA='sld-beta3-integrated-case/v1'


def _indexes(pages:list[dict]) -> dict[str,list[dict]]:
    result=defaultdict(list)
    for page in pages:
        if page.get('page_type')=='ERROR':continue
        for a in page.get('text_equipment_anchors',[]):
            tag=a.get('tag')
            if not tag or a.get('anchor_role') not in ('INSTANCE','TAG'):
                continue
            norm=' '.join(tag.upper().split())
            result[norm].append({'tag':tag,'page':page['page'],
                                 'anchor_id':a.get('anchor_id'),
                                 'equipment_type':a.get('equipment_type'),
                                 'role':a.get('anchor_role'),
                                 'source':a.get('source'),
                                 'bbox':a.get('bbox')})
    return dict(result)


def cross_source_occurrences(sld_pages:list[dict],layout_pages:list[dict]) -> list[dict]:
    """Exact tag correspondence: evidence of same spelling, NOT asset identity.

    No undocumented alias or single arbitrary choice among repeated labels.
    """
    sld=_indexes(sld_pages);layout=_indexes(layout_pages)
    result=[]
    for tag in sorted(sld.keys()&layout.keys()):
        left,right=sld[tag],layout[tag]
        result.append({'normalized_tag':tag,'sld_occurrences':left,
                       'layout_occurrences':right,
                       'status':'CANDIDATE_EXACT_TAG_CROSS_SOURCE',
                       'unique_both_sources':len(left)==len(right)==1,
                       'identity_verified_by_tag_only':False,
                       'note':'Exact spelling is a correlation candidate, not a topology link'})
    return result


def _membership_provenance(reconciliation:dict, verification:dict) -> dict:
    """Disjoint reporting layers; preserve actual membership evidence rows.

    Structural assignments are not explicit-schedule rows and are not graph
    verification. A single CU appears once in the canonical reconciliation.
    """
    assignments=reconciliation.get('cu_mv_membership') or []
    inferred=[m for m in assignments if m.get('source_status')=='INFERRED']
    explicit=[m for m in assignments if m.get('source_status')=='DETECTED']
    other=[m for m in assignments if m.get('source_status') not in ('INFERRED','DETECTED')]
    schedule=verification.get('explicit_schedule_membership') or []
    graphs=verification.get('graph_verified_membership') or []
    return {'canonical_cu_feeder_membership_count':len(assignments),
            'structural_inferred_count':len(inferred),
            'explicit_schedule_membership_count':len(schedule),
            'canonical_detected_count':len(explicit),
            'other_canonical_count':len(other),
            'graph_verified_membership_count':len(graphs),
            'structural_inferred':inferred,
            'canonical_detected':explicit,
            'other_canonical':other,
            'status':'INDEPENDENT_PROVENANCE_LAYERS',
            'warning':'These categories can overlap in identity; do not sum them as distinct CU assets'}


def summarize_legacy(base:dict) -> dict:
    """Source of truth for existing document inference: no recomputed counts."""
    fv=base.get('feeder_verification') or {}
    reconciliation=base.get('source_reconciliation') or {}
    sources=base.get('sources') or {}
    sld_source=sources.get('sld') or {}
    layout_source=sources.get('layout') or {}
    return {
      'plant_id':(base.get('plant') or {}).get('plant_id'),
      'target_counts':base.get('target_counts') or {},
      'legacy_documental_membership':{
          'explicit_schedule_membership':fv.get('explicit_schedule_membership') or [],
          'summary':fv.get('summary') or {},
      },
      'legacy_graph_verification':{
          'verified_membership':fv.get('graph_verified_membership') or [],
          'summary_count':(fv.get('summary') or {}).get('graph_verified_cu_mv_membership_count',0),
          'attribution':'DEV14C_INDEPENDENT_OF_BETA3',
      },
      'canonical_identity_summary':reconciliation.get('summary') or {},
      'membership_provenance': _membership_provenance(reconciliation,fv),
      'source_coverage':{'sld':sld_source,'layout':layout_source},
      'partial_sources':not (sld_source.get('analysis_complete',False) and
                            (not layout_source.get('present',True) or layout_source.get('analysis_complete',False))),
    }


def assemble_report(base:dict, *, sld_path:str|Path,
                    layout_path:str|Path|None=None, max_pairs:int=4,
                    max_strokes:int=1200, padding:float=45,
                    max_neighborhoods:int=3,
                   geometry_first_pages:int=0,
                   baseline_json_path:str|Path|None=None) -> dict:
    if max_pairs<0:raise ValueError('max_pairs negative')
    sld_pages=base.get('pages') or []
    layout_pages=base.get('layout_pages') or []
    checks=[]; candidates=[]; errors=[]
    for page in sld_pages:
        if len(checks)>=max_pairs:break
        if page.get('page_type')=='ERROR':
            errors.append({'page':page.get('page'),'reason':'DEV14C_PAGE_ERROR',
                           'detail':page.get('error')});continue
        pairs=plan_pairs(page,max_pairs=max_pairs-len(checks))
        for a,b in pairs:
            try:
                check=inspect_pair(sld_path,int(page['page']),a,b,
                                   max_strokes=max_strokes,padding=padding)
                checks.append(check)
            except Exception as exc:
                errors.append({'page':page.get('page'),
                               'symbol_ids':[a.get('symbol_id'),b.get('symbol_id')],
                               'reason':'BETA3_LOCAL_INSPECTION_ERROR',
                               'detail':str(exc)})
    for page in sld_pages:
        for s in page.get('symbol_candidates',[]):
            if s.get('evidence_state')=='FUSED' and s.get('tag') and s.get('terminals'):
                candidates.append({'page':page.get('page'),'symbol_id':s.get('symbol_id'),
                                   'tag':s.get('tag'),'candidate_type':s.get('candidate_type'),
                                   'terminal_count':len(s['terminals']),
                                   'evidence_state':'FUSED','electrical_role_verified':False})
    identity_queue=plan_cu_verifications(base)
    neighborhoods=inspect_identity_neighborhoods(sld_path,identity_queue,
             max_inspections=max_neighborhoods,padding=padding,max_strokes=max_strokes)
    counts=Counter(x['trace']['status'] for x in checks)
    legacy=summarize_legacy(base)
    coverage=legacy['source_coverage']
    incomplete=legacy['partial_sources'] or bool(errors)
    return {
       'schema':SCHEMA,'status':'PARTIAL' if incomplete else 'COMPLETE_INTEGRATION_DIAGNOSTIC',
       'plant_id':legacy['plant_id'],'input_files':{'sld':Path(sld_path).name,
                    'layout':Path(layout_path).name if layout_path else None},
       'ground_truth_used':False,'expected_counts_used':False,
       'inference_modified_by_beta3':False,'dev14c_modified':False,
       'legacy_inference':legacy,
       'cross_source_tag_correspondences':cross_source_occurrences(sld_pages,layout_pages),
       'beta3_identity_verification_queue':identity_queue,
       'beta3_cross_sheet_references':analyze_cross_sheet(base),
       'beta3_cu_neighborhood_inspections':neighborhoods,
       'beta3_geometry':{
          'fused_named_symbols_with_terminals':candidates,
          'pair_inspections':checks,'error_diagnostics':errors,
          'summary':{'inspections_completed':len(checks),
                     'inspection_budget':max_pairs,
                     'cu_identity_tasks':identity_queue['summary']['canonical_cu_tasks'],
                     'cu_neighborhoods_inspected':len(neighborhoods),
                     'named_fused_symbol_count':len(candidates),
                     'local_geometric_path_candidates':counts['LOCAL_GEOMETRIC_PATH_CANDIDATE'],
                     'disconnected_in_roi':counts['DISCONNECTED_IN_ROI'],
                     'unresolved_in_roi':counts['UNRESOLVED'],
                     'beta3_graph_verified_feeder_membership':0,
                     'reason':'No complete feeder root to CU trace established by beta3'},
       },
       'evaluation':{
           'end_to_end_beta3_electrical_feeder_path_verified':False,
           'whole_plant_beta3_graph_completed':False,
           'counts_not_sourced_from_regression_oracle':True,
           'notes':['Legacy hierarchy/membership originates from an unchanged independent dev14c run.',
                    'Beta3 ROI inspection does not change, confirm or reject dev14c document inference.',
                    'Cross-source exact tag matches are not enough to assert identical physical assets.',
                    'Reciprocal cross-sheet links are documentary links, not through-device electrical paths.',
                    'No Ground Truth or benchmark counts are accessible to the inference pipeline.']
       },
    }


def run_integrated(sld_path:str|Path, out_dir:str|Path, *,
                   layout_path:str|Path|None=None, plant_id:str|None=None,
                   max_pages:int|None=None, max_pairs:int=4,
                   max_strokes:int=1200, padding:float=45,
                   ocr_mode:str='auto', knowledge_path:str|None=None,
                   operator_feedback_path:str|None=None,
                   max_neighborhoods:int=3,
                   geometry_first_pages:int=0,
                   baseline_json_path:str|Path|None=None) -> dict:
    """Run unchanged beta2 inference and beta3 diagnostics into a dedicated directory."""
    sld=Path(sld_path)
    if not sld.is_file() or sld.suffix.lower()!='.pdf':
        raise FileNotFoundError(f'SLD PDF required: {sld}')
    if layout_path is not None and (not Path(layout_path).is_file() or Path(layout_path).suffix.lower()!='.pdf'):
        raise FileNotFoundError(f'LAYOUT PDF required: {layout_path}')
    if max_pages is not None and max_pages<1:raise ValueError('max_pages invalid')
    out=Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    baseline_reused=baseline_json_path is not None
    if baseline_reused:
        if knowledge_path or operator_feedback_path:
            raise ValueError('Do not add operator knowledge to a previously computed baseline; execute a fresh inference')
        import pymupdf
        src=Path(baseline_json_path)
        if not src.is_file():raise FileNotFoundError(src)
        base=json.loads(src.read_text(encoding='utf8'))
        pid=validate_source_pair(str(sld),str(layout_path) if layout_path else None,plant_id=plant_id)['plant_id']
        if (base.get('plant') or {}).get('plant_id')!=pid:
            raise ValueError('Baseline plant ID mismatch')
        sources=base.get('sources') or {}
        for kind,docpath in (('sld',sld),('layout',Path(layout_path) if layout_path else None)):
            evidence=sources.get(kind) or {}
            if docpath is None:
                if evidence and evidence.get('file_name'):
                    raise ValueError(f'Baseline unexpectedly contains {kind} input')
                continue
            with pymupdf.open(str(docpath)) as pdf:
                observed=len(pdf)
            if evidence.get('file_name')!=docpath.name or evidence.get('page_count')!=observed:
                raise ValueError(f'Baseline {kind} file name/page count mismatch')
        knowledge_audit={'canonical_plant_id':pid,'knowledge_supplied':False,
            'operator_feedback_supplied':False,'included_patterns':0,'excluded_patterns':0,
            'isolation':'ALREADY_COMPUTED_BASELINE','original_files_modified':False}
    else:
        cfg=RunConfig(max_pages=max_pages, ocr_mode=ocr_mode)
        staged, knowledge_audit=stage_knowledge(knowledge_path=knowledge_path,
                feedback_path=operator_feedback_path,out_dir=out,
                sld_path=sld,layout_path=layout_path,plant_id=plant_id)
        base=run_case(str(sld),str(out/'dev14c_inference.json'),cfg,
                  layout_path=str(layout_path) if layout_path else None,
                  plant_id=plant_id,
                  knowledge_path=staged['knowledge'],
                  operator_feedback_path=staged['feedback'])
    report=assemble_report(base,sld_path=sld,layout_path=layout_path,
                           max_pairs=max_pairs,max_strokes=max_strokes,padding=padding,
                           max_neighborhoods=max_neighborhoods)
    # Alpha5: generalizable, read-only page routing is also part of the
    # end-to-end diagnostic output. It NEVER changes dev14c or promotes tags,
    # MATCHLINE, OCR, or local vector strokes to electrical connections.
    from .multistyle import audit_multistyle
    routes=audit_multistyle(sld,max_pages=max_pages,max_probe_pages=2,
                            regions_per_page=2,ocr_preview=False,
                            geometry_first_pages=geometry_first_pages,
                            plant_id=report['plant_id'])
    multistyle_dest=out/'multistyle_preflight.json'
    multistyle_dest.write_text(json.dumps(routes,ensure_ascii=False,indent=2),encoding='utf-8')
    report['beta3_multistyle_preflight']={
        'schema':routes['schema'], 'status':routes['status'],
        'summary':routes['summary'],
        'page_routes':[{'page':row['page'],'modes':row['modes'],
                        'device_tag_occurrences':len(row['named_devices']),
                        'reference_occurrences':len(row['references']),
                        'geometry_status':row['geometry_status'],
                        'alpha8_geometry_first_status':row['geometry_first']['status'],
                        'alpha8_shape_hypotheses_unverified':len(row['geometry_first']['hypotheses']),
                        'vector_review_regions':len(row['local_vector_reviews'])}
                       for row in routes['pages']],
        'independent_of_legacy_counts':True,
        'electrical_paths_verified':False,
        'detail_report':'multistyle_preflight.json',
    }
    # Alpha6: provenance layers must not be mixed or added as equipment counts.
    legacy_provenance=report['legacy_inference']['membership_provenance']
    report['beta3_count_provenance']={
        'native_pdf_tag_mentions':routes['count_provenance']['native_pdf_tag_mentions'],
        'unverified_unique_type_tag_keys':routes['count_provenance']['unique_tag_type_keys_UNVERIFIED'],
        'legacy_resolved_hierarchy_totals_unsplit_by_source':report['legacy_inference']['target_counts'],
        'layout_or_other_structurally_inferred_cu_feeder_relations':legacy_provenance['structural_inferred_count'],
        'explicit_schedule_documented_cu_feeder_relations':legacy_provenance['explicit_schedule_membership_count'],
        'graph_verified_cu_feeder_relations':legacy_provenance['graph_verified_membership_count'],
        'diagram_symbol_qualified_physical_device_counts':None,
        'equipment_counts_extracted_from_explicit_tables':None,
        'equipment_counts_derived_by_inference_rules':None,
        'physical_asset_deduplicated_counts_by_type':None,
        'status':'SEPARATE_PROVENANCE_NOT_ADDITIVE',
        'warning':'Legacy aggregate equipment counts cannot be split into diagram/table/inferred categories at individual asset level from the available summary; unknown is null, not zero.'}
    report['operator_knowledge_audit']=knowledge_audit
    report['baseline_reuse']={'reused':baseline_reused,
         'baseline_source':str(baseline_json_path) if baseline_reused else 'FRESH_DEV14C_RUN',
         'validation':'PLANT_ID_FILENAME_PAGE_COUNT_ONLY' if baseline_reused else 'CURRENT_INFERENCE',
         'warning':('Baseline JSON cannot establish byte-identical PDF sources without original content hashes'
                    if baseline_reused else None)}
    report['outputs']={'dev14c_inference':str(baseline_json_path) if baseline_reused else 'dev14c_inference.json',
                       'integrated_report':'integrated_report.json',
                       'multistyle_preflight':'multistyle_preflight.json'}
    dest=out/'integrated_report.json'
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
