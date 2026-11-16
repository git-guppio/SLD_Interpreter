"""Read-only parallel geometry comparison of dev14c and beta3 on the same PDF page.

Neither output nor this module is connected to the inference/GT pathway.
Use only comparison measurements; component counts are not automatically equivalent
because the geometric acceptance policies differ.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import pymupdf
from .geometry.kernel import extract_pdf, build_graph
from .geometry.classify import classify_strokes
from sld_ci_v04_beta2_dev14c.config import GeometryThresholds
from sld_ci_v04_beta2_dev14c.ingestion import extract_orthogonal_vector_inventory
from sld_ci_v04_beta2_dev14c.vector_graph import build_electrical_planar_graph


def compare_page(page: pymupdf.Page, page_number: int, *, max_strokes: int = 1200, roi=None) -> dict[str, Any]:
    if max_strokes < 1:
        raise ValueError('max_strokes must be >= 1')
    cfg = GeometryThresholds()
    started = time.perf_counter()
    inventory = extract_orthogonal_vector_inventory(page, cfg)
    b2_segs = inventory['accepted_segments']
    b3_raw, ignored, dots = extract_pdf(page, page_number=page_number)
    b3_segs, classification = classify_strokes(b3_raw, roi=roi)
    if roi is not None:
        x0,y0,x1,y1=roi
        dots=[p for p in dots if x0<=p[0]<=x1 and y0<=p[1]<=y1]
    report = {
        'page':page_number, 'mode':'SHADOW_COMPARISON_ONLY',
        'source':{'width_pt':float(page.rect.width), 'height_pt':float(page.rect.height)},
        'dev14c':{'accepted_segments':len(b2_segs),'inventory_truncated':bool(inventory.get('scan_truncated')),
                  'profile_by_stroke_color':inventory.get('profile_by_stroke_color',{}), 'status':'NOT_RUN'},
        'beta3':{'extracted_strokes':len(b3_raw),'retained_candidates':len(b3_segs), 'classification':classification, 'junction_dot_candidates':len(dots),
                 'ignored_drawing_items':len(ignored), 'status':'NOT_RUN'},
        'comparison':{'status':'NOT_COMPARABLE','reason':'Connectivity policies differ; never infer asset counts or feeder membership from these metrics'},
        'warnings':[],
    }
    if inventory.get('scan_truncated'):
        report['warnings'].append({'code':'DEV14C_INVENTORY_TRUNCATED'})
    if len(b2_segs)>max_strokes:
        report['dev14c'].update(status='INCOMPLETE', reason='SAFETY_CAP', limit=max_strokes)
    else:
        old = build_electrical_planar_graph(b2_segs, inventory['page_width_pt'], inventory['page_height_pt'], cfg)
        report['dev14c'].update(status='COMPLETE', node_count=len(old['nodes']), edge_count=len(old['edges']),
                                component_count=old['connected_component_count'], crossing_count=len(old['crossings']))
    if roi is not None:
        report['warnings'].append({'code':'ROI_ONLY_NOT_FULL_PAGE','message':'ROI is diagnostic; no full-page connectivity claim'})
    if len(b3_segs)>max_strokes:
        report['beta3'].update(status='INCOMPLETE', reason='SAFETY_CAP', limit=max_strokes)
    else:
        new = build_graph(b3_segs,dots=dots,max_strokes=max_strokes)
        report['beta3'].update(status=new['status'], node_count=new['node_count'],edge_count=new['edge_count'],
                              component_count=new['component_count'], crossing_count=len(new.get('crossings',[])),
                              warnings=new['warnings'])
    if report['dev14c']['status']=='COMPLETE' and report['beta3']['status']=='COMPLETE':
        report['comparison'].update(status='METRICS_AVAILABLE' if roi is None else 'ROI_DIAGNOSTIC_ONLY',delta_segments=len(b3_segs)-len(b2_segs),
                                    delta_components=report['beta3']['component_count']-report['dev14c']['component_count'])
    else:
        report['warnings'].append({'code':'COMPARISON_INCOMPLETE','message':'At least one geometry run exceeds a cap or is truncated'})
    report['elapsed_seconds']=round(time.perf_counter()-started,3)
    return report


def compare_pdf(path: str | Path, *, pages: list[int], max_strokes: int=1200, roi=None) -> dict[str, Any]:
    pdf_path=Path(path)
    if not pdf_path.is_file(): raise FileNotFoundError(pdf_path)
    results=[]
    with pymupdf.open(pdf_path) as doc:
        for p in pages:
            if p<1 or p>len(doc): raise ValueError(f'page {p} outside 1..{len(doc)}')
            results.append(compare_page(doc[p-1],p,max_strokes=max_strokes,roi=roi))
        return {'schema':'sld-shadow-comparison/v1', 'status':'COMPLETE' if all(
                r['comparison']['status']=='METRICS_AVAILABLE' and not r['dev14c']['inventory_truncated'] for r in results) else 'PARTIAL',
                'pdf_name':pdf_path.name,'page_count':len(doc),'pages':results,
                'ground_truth_used':False,'inference_modified':False,
                'note':'Diagnostic geometry counts are not plant/asset/feeder regressions.'}


def main():
    ap=argparse.ArgumentParser(description='Confronto parallelo e non invasivo geometria dev14c/beta3')
    ap.add_argument('--pdf',required=True)
    ap.add_argument('--pages',type=int,nargs='+',default=[1])
    ap.add_argument('--out',required=True)
    ap.add_argument('--max-strokes',type=int,default=1200)
    ap.add_argument('--roi',type=float,nargs=4,metavar=('X0','Y0','X1','Y1'),help='Bounding box in PDF points; diagnostic only')
    args=ap.parse_args()
    r=compare_pdf(args.pdf,pages=args.pages,max_strokes=args.max_strokes,roi=args.roi)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"{r['status']}: {r['pdf_name']}")
    for pg in r['pages']:
        a=pg['dev14c']; b=pg['beta3']
        print(f"  pag. {pg['page']}: dev14c={a['status']} ({a['accepted_segments']} tratti), "
              f"beta3={b['status']} ({b['extracted_strokes']} grezzi, {b['retained_candidates']} candidati); confronto={pg['comparison']['status']}")
    print('Report:',out)

if __name__=='__main__':main()
