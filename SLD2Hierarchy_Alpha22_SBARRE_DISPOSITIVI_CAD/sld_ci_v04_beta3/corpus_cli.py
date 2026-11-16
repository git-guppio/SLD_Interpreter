"""Alpha6 multi-plant validation on real PDFs, optional independent tag truth."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from .integration.corpus_benchmark import run_corpus

def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha6: corpus test, no expected counts used for inference')
    p.add_argument('--manifest',required=True)
    p.add_argument('--max-pages',type=int)
    p.add_argument('--max-probe-pages',type=int,default=1)
    p.add_argument('--regions-per-page',type=int,default=1)
    p.add_argument('--out-json',default='reports/corpus_audit.json')
    args=p.parse_args(argv)
    r=run_corpus(args.manifest,max_pages=args.max_pages,
                 max_probe_pages=args.max_probe_pages,regions_per_page=args.regions_per_page)
    dst=Path(args.out_json);dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    with dst.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['case','pages_scanned','native_tag_occurrences','unverified_tag_keys',
            'geometry_regions','roi_caps','tag_precision','tag_recall','asset_precision','asset_recall'])
        for x in r['cases']:
            a=x['summary'];z=x['tag_score']
            w.writerow([x['case_id'],a['pages_scanned'],a['device_tag_occurrences'],
                 a['unverified_distinct_tag_type_pairs'],a['local_vector_review_regions'],
                 a['roi_safety_cap_regions'],z['tag_level_precision'],z['tag_level_recall'],
                 'NOT_AVAILABLE','NOT_AVAILABLE'])
    for x in r['cases']:
        s=x['summary'];print(x['case_id'], 'pages',s['pages_scanned'],
            'tag_mentions',s['device_tag_occurrences'],'ROI',s['local_vector_review_regions'],
            'tag_scoring',x['tag_score']['status'])
    print('Corpus report:',dst,'CSV:',dst.with_suffix('.csv'))
    return 0
if __name__=='__main__':raise SystemExit(main())
