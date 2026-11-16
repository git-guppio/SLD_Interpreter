"""Read-only cross-sheet documentary diagnostics from an existing dev14c run."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from .integration.cross_sheet import analyze_cross_sheet


def main():
    p=argparse.ArgumentParser(description='Cross-sheet references, documentary evidence only')
    p.add_argument('--baseline-json',required=True,help='Existing dev14c_inference.json; never modified')
    p.add_argument('--out-json',default='reports/cross_sheet_reference_graph.json')
    args=p.parse_args()
    baseline=Path(args.baseline_json)
    if not baseline.is_file():
        p.error(f'File not found: {baseline}')
    base=json.loads(baseline.read_text(encoding='utf-8'))
    result=analyze_cross_sheet(base)
    target=Path(args.out_json)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    csv_path=target.with_suffix('.csv')
    with csv_path.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f,delimiter=';')
        writer.writerow(['from_cu','to_cu','status','page_from','anchor_from','page_to','anchor_to','electrical_verified'])
        for link in result['reciprocal_links']+result['incomplete_links']:
            refs=link['evidence']; sides={r['reference_side']:r for r in refs}
            a,b=sides.get('ORIGIN_PAGE_TO',{}),sides.get('DESTINATION_PAGE_FROM',{})
            writer.writerow([link['from_instance_key'],link['to_instance_key'],link['status'],
                             a.get('page',''),a.get('anchor_id',''),b.get('page',''),b.get('anchor_id',''),'NO'])
    s=result['summary'];c=result['independent_layout_comparison']
    print('\n--- RIMANDI TRA PAGINE / SOLO EVIDENZE DOCUMENTALI ---')
    print('Impianto:',result['plant_id'])
    print('Link reciproci:',s['reciprocal_documentary_links'])
    print('Link incompleti/ambigui:',s['one_sided_or_ambiguous_links'])
    print('Gruppi indipendenti:',s['cross_sheet_groups'],'dimensioni:',s['group_sizes'])
    print('Concordanza post-hoc con assegnazione layout:',c['same_layout_feeder'],'/',c['comparable_links'])
    print('Percorsi elettrici feeder-CU verificati:',s['electrical_paths_verified'])
    print('JSON:',target,'\nCSV:',csv_path)

if __name__=='__main__':main()
