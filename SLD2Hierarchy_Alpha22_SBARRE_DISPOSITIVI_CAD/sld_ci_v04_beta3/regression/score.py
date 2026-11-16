"""Post-run scorer only. Separate process from inference; accepts existing JSON output."""
import argparse,json
from pathlib import Path
def read_counts(out):
    tc=out.get('target_counts',{}) or {}
    fv=(out.get('feeder_verification',{}) or {}).get('summary',{}) or {}
    sr=(out.get('source_reconciliation',{}) or {}).get('summary',{}) or {}
    return {
        'conversion_units':tc.get('conversion_units'),
        'mv_lv_transformers':tc.get('mv_lv_transformers'),
        'inverters':tc.get('inverters'),
        'string_boxes':tc.get('string_boxes'),
        'mv_feeders':sr.get('mv_line_count') if sr.get('mv_line_count') is not None else fv.get('explicit_schedule_feeder_count'),
        'resolved_cu_mv_membership':sr.get('resolved_cu_mv_membership_count'),
        'graph_verified_cu_mv_membership':fv.get('graph_verified_cu_mv_membership_count'),
    }
def score(case,output_path,oracle_path):
    expected=json.loads(Path(oracle_path).read_text(encoding='utf8'))['cases'][case]['expected']
    actual=read_counts(json.loads(Path(output_path).read_text(encoding='utf8')))
    checked={}
    for key,target in expected.items():
        observed=actual.get(key)
        checked[key]={'expected':target,'actual':observed,'status':'PASS' if observed==target else ('NOT_REPORTED' if observed is None else 'FAIL')}
    return {'case':case,'metrics':checked,'pass':all(x['status']=='PASS' for x in checked.values()),
            'note':'Post-run diagnostic only. Exact counts do not establish precision/recall or graph connectivity.'}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--case',required=True,choices=['CASE_004_PV4','CASE_008_PV8'])
    ap.add_argument('--output',required=True)
    ap.add_argument('--oracle',default=str(Path(__file__).with_name('oracle.json')))
    args=ap.parse_args()
    report=score(args.case,args.output,args.oracle)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    raise SystemExit(0 if report['pass'] else 2)
if __name__=='__main__':main()
