"""Read-only corpus audit and independently supervised TAG-level scoring.

The reference annotations are never exposed to inference. Counts-only oracle
files are intentionally insufficient for computing precision and recall.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json
from .multistyle import audit_multistyle, _canonical_tag


def compare_annotated_tags(audit, gold):
    """Strict type+tag matching; score tag extraction, NOT physical instances.

    Gold must contain independently annotated, unique tag/type identities.
    Duplicate physical assets with one reused tag cannot be resolved here and
    must be reported separately, not silently counted as one true asset.
    """
    if gold is None:
        return {'status':'NOT_SCORABLE_MISSING_INSTANCE_ANNOTATIONS',
                'tag_level_precision':None,'tag_level_recall':None,
                'physical_asset_precision':None,'physical_asset_recall':None,
                'by_device_type':{},
                'reason':'Count-only truth and inferred totals do not identify individual true/false detections'}
    if not isinstance(gold,list):raise ValueError('annotations must be a list')
    gt=set()
    for row in gold:
        if not isinstance(row,dict) or not row.get('tag_type') or not row.get('tag'):
            raise ValueError('annotations require tag_type and tag')
        k=(row['tag_type'].strip().upper(),_canonical_tag(row['tag_type'].strip().upper(),row['tag']))
        if k in gt:raise ValueError('duplicated reference tag identity; annotate physical instances separately')
        gt.add(k)
    pred={(g['tag_type'],g['tag']) for g in audit['tag_identity_groups']}
    stats={}
    for typ in sorted({k[0] for k in gt|pred}):
        t={v for v in gt if v[0]==typ};p={v for v in pred if v[0]==typ}
        tp=len(t&p);fp=len(p-t);fn=len(t-p)
        stats[typ]={'TP':tp,'FP':fp,'FN':fn,
                    'tag_level_precision':tp/(tp+fp) if tp+fp else None,
                    'tag_level_recall':tp/(tp+fn) if tp+fn else None,
                    'example_false_positives':sorted([v[1] for v in p-t])[:10],
                    'example_false_negatives':sorted([v[1] for v in t-p])[:10],
                    'scoring_scope':'TAG_TYPE_TAG_NOT_PHYSICAL_DEVICE_INSTANCE'}
    tp=len(pred&gt);fp=len(pred-gt);fn=len(gt-pred)
    return {'status':'TAG_LEVEL_SCORABLE_NOT_ASSET_DETECTION',
            'TP':tp,'FP':fp,'FN':fn,
            'tag_level_precision':tp/(tp+fp) if tp+fp else None,
            'tag_level_recall':tp/(tp+fn) if tp+fn else None,
            'physical_asset_precision':None,'physical_asset_recall':None,
            'by_device_type':stats,
            'reason':'Device-level accuracy requires independent instance IDs, bounding regions, source linkage and duplicate resolution'}


def run_corpus(manifest, *, max_pages=None, max_probe_pages=1,regions_per_page=1):
    """Corpus manifest cases [{case_id,pdf,plant_id,annotation_file?}]."""
    manifest=Path(manifest).resolve()
    cfg=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if not isinstance(cfg.get('cases'),list):raise ValueError('manifest must contain cases list')
    seen=set(); rows=[]
    for case in cfg['cases']:
        cid=str(case['case_id'])
        if cid in seen:raise ValueError('duplicate case_id')
        seen.add(cid)
        pdf=Path(case['pdf'])
        if not pdf.is_absolute():pdf=(manifest.parent/pdf).resolve()
        # independent inference -- never supply annotations/count truth to it
        audit=audit_multistyle(pdf,plant_id=case.get('plant_id'),
            max_pages=max_pages,max_probe_pages=max_probe_pages,
            regions_per_page=regions_per_page,ocr_preview=False)
        gold=None
        if case.get('annotation_file'):
            ann=Path(case['annotation_file'])
            if not ann.is_absolute():ann=(manifest.parent/ann).resolve()
            dat=json.loads(ann.read_text(encoding='utf-8-sig'))
            gold=dat.get('tag_annotations')
            if gold is None:raise ValueError('annotation_file requires tag_annotations, even if []')
        score=compare_annotated_tags(audit,gold)
        rows.append({'case_id':cid,'pdf':str(pdf),'status':audit['status'],
                     'summary':audit['summary'],
                     'by_tag_type':dict(Counter(g['tag_type'] for g in audit['tag_identity_groups'])),
                     'tag_score':score,'geometry_status_by_page':[
                         {'page':r['page'],'status':r['geometry_status'],
                          'region_count':len(r['local_vector_reviews'])} for r in audit['pages']],
                     'physical_asset_instance_scoring':'NOT_AVAILABLE_WITH_TAG_ONLY_PRE-FLIGHT'})
    return {'schema':'sld-beta3-corpus-audit/v1','cases':rows,
        'count_truth_accessed_during_inference':False,
        'physical_asset_precision_recall_available':False,
        'warning':'Tag extraction benchmark is not an electrical asset detection benchmark. Independent per-instance annotations are required.'}
