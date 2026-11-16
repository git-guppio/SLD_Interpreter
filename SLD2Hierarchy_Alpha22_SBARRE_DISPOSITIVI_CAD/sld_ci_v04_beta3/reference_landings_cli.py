"""Read-only PDF cross-sheet landing diagnostics."""
import argparse,csv,json
from pathlib import Path
from .integration.reference_landings import analyze_reference_landings

def main():
    a=argparse.ArgumentParser(description='Reference-to-vector strokes, NOT electrical continuity')
    a.add_argument('--baseline-json', required=True)
    a.add_argument('--sld-pdf', required=True)
    a.add_argument('--pages', help='comma-separated 1-based pages for a diagnostic sample')
    a.add_argument('--out-json',default='reports/reference_landings.json')
    args=a.parse_args()
    base=json.loads(Path(args.baseline_json).read_text(encoding='utf-8'))
    pages=set(map(int,args.pages.split(','))) if args.pages else None
    result=analyze_reference_landings(base,args.sld_pdf,selected_pages=pages)
    dest=Path(args.out_json);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    csvpath=dest.with_suffix('.csv')
    with csvpath.open('w',newline='',encoding='utf-8-sig') as fd:
        wr=csv.writer(fd,delimiter=';')
        wr.writerow(['from_cu','to_cu','side','page','label','status','stroke_id','near_cell_line_text','electrical_verified'])
        for row in result['landings']:
            wr.writerow([row['from_instance_key'],row['to_instance_key'],row['reference_side'],
                         row['page'],row['reference_text'],row['status'],
                         (row['vector_stroke'] or {}).get('source_stroke_id',''),
                         'YES' if row['adjacent_mv_line_cell_text_cue'] else 'NO','NO'])
    print('--- CANDIDATI DI APPRODO RIMANDI -> VETTORI ---')
    for k,v in result['summary'].items():print(k,':',v)
    print('ATTENZIONE: approdi candidati, ZERO continuita attraverso celle verificata')
    print('JSON:',dest,'CSV:',csvpath)

if __name__=='__main__':main()
