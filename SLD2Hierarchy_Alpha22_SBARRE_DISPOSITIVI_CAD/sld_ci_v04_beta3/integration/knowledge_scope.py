"""Strict read-only per-plant operator learning adapter.

Works *outside* frozen dev14c. Only explicit, matching PLANT-scoped
operator knowledge/feedback is forwarded. User-provided source is never saved.
"""
from __future__ import annotations
import json
from pathlib import Path
from sld_ci_v04_beta2_dev14c.source_resolution import validate_source_pair


def _origin(row):
    return row.get('origin_plant_id') or row.get('plant_id') or (row.get('context') or {}).get('plant_id')


def select_scoped_knowledge(store_obj:dict,plant_id:str) -> dict:
    if not isinstance(store_obj,dict):raise ValueError('knowledge store must be JSON object')
    filtered=dict(store_obj)
    src=store_obj.get('patterns',[])
    if not isinstance(src,list):raise ValueError('knowledge patterns must be list')
    filtered['patterns']=[p for p in src if isinstance(p,dict)
        and str(p.get('scope','')).upper()=='PLANT' and str(_origin(p))==plant_id]
    # Feedback historically stored here is not automatically active in dev14c;
    # exclude to avoid exporting unrelated plant observations to the working copy.
    filtered['operator_feedback']=[]
    return filtered


def select_scoped_feedback(obj,plant_id:str):
    rows=obj
    if isinstance(rows,dict): rows=rows.get('operator_feedback',rows.get('records',[]))
    if not isinstance(rows,list):raise ValueError('operator feedback must be JSON list')
    active=[]
    for r in rows:
        if not isinstance(r,dict):raise ValueError('feedback item must be JSON object')
        if r.get('status')=='OPERATOR_PROVIDED':
            source=_origin(r)
            if not source or str(source)!=plant_id:
                raise ValueError('Active operator feedback must carry the exact current plant_id; no cross-plant reuse')
        active.append(r)
    return active


def stage_knowledge(*,knowledge_path,feedback_path,out_dir,sld_path,layout_path,plant_id):
    """Return vetted local copies and provenance; never write user's originals.

    No knowledge input means no learned patterns; no silent global store.
    """
    pid=validate_source_pair(str(sld_path),str(layout_path) if layout_path else None,plant_id=plant_id)['plant_id']
    out=Path(out_dir); paths={'knowledge':None,'feedback':None}
    stats={'canonical_plant_id':pid,'knowledge_supplied':bool(knowledge_path),
           'operator_feedback_supplied':bool(feedback_path),'included_patterns':0,
           'excluded_patterns':0,'isolation':'PLANT_ONLY','original_files_modified':False}
    if knowledge_path:
        src=Path(knowledge_path)
        if not src.is_file():raise FileNotFoundError(src)
        obj=json.loads(src.read_text(encoding='utf8'))
        filtered=select_scoped_knowledge(obj,pid)
        stats['included_patterns']=len(filtered['patterns'])
        stats['excluded_patterns']=len(obj.get('patterns',[]))-len(filtered['patterns'])
        out.mkdir(parents=True,exist_ok=True)
        dest=out/'knowledge_store_plant_scoped_working_copy.json'
        if dest.resolve()==src.resolve():raise ValueError('knowledge source cannot be in-place working copy')
        dest.write_text(json.dumps(filtered,indent=2,ensure_ascii=False),encoding='utf8')
        paths['knowledge']=str(dest)
    if feedback_path:
        src=Path(feedback_path)
        if not src.is_file():raise FileNotFoundError(src)
        data=select_scoped_feedback(json.loads(src.read_text(encoding='utf8')),pid)
        out.mkdir(parents=True,exist_ok=True)
        dest=out/'operator_feedback_plant_scoped_working_copy.json'
        if dest.resolve()==src.resolve():raise ValueError('feedback source cannot be in-place working copy')
        dest.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
        paths['feedback']=str(dest)
        stats['forwarded_feedback_records']=len(data)
    return paths,stats
