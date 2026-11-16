"""Alpha 7 multistyle SLD diagnostic entry point."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from .integration.multistyle import audit_multistyle


def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha7: diagnosi multimodale senza collegamenti elettrici inventati')
    p.add_argument('--pdf',required=True)
    p.add_argument('--plant-id')
    p.add_argument('--max-pages',type=int)
    p.add_argument('--max-probe-pages',type=int,default=3)
    p.add_argument('--regions-per-page',type=int,default=3)
    p.add_argument('--max-drawings',type=int,default=8500)
    p.add_argument('--ocr-preview',action='store_true',help='OCR opzionale solo su pagine senza testo; Tesseract richiesto')
    p.add_argument('--max-ocr-pages',type=int,default=1)
    p.add_argument('--out-json',default='reports/multistyle_preflight.json')
    args=p.parse_args(argv)
    r=audit_multistyle(args.pdf,max_pages=args.max_pages,max_probe_pages=args.max_probe_pages,
        regions_per_page=args.regions_per_page,max_drawings=args.max_drawings,
        ocr_preview=args.ocr_preview,max_ocr_pages=args.max_ocr_pages,plant_id=args.plant_id)
    out=Path(args.out_json);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    with out.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['page','modes','native_text_lines','device_tags','references','geometry_status','vector_review_regions','roi_caps','short_segments','ocr_status','symbol_hypotheses_unverified','possible_contacts_unverified','electric_paths_verified'])
        for row in r['pages']:
            w.writerow([row['page'],','.join(row['modes']),row['native_text_lines'],len(row['named_devices']),
                len(row['references']),row['geometry_status'],len(row['local_vector_reviews']),
                sum('SAFETY_CAP' in r['status'] for r in row['local_vector_reviews']),
                sum(r.get('short_segment_candidates') or 0 for r in row['local_vector_reviews']),
                row['ocr_preview']['status'],
                sum(len(rr.get('alpha7_symbol_terminal',{}).get('symbol_hypotheses',[])) for rr in row['local_vector_reviews']),
                sum(len(rr.get('alpha7_symbol_terminal',{}).get('possible_contact_points',[])) for rr in row['local_vector_reviews']),
                row['graph_verified_electrical_connections']])
    print('--- ALPHA 7 - TRIAGE SLD MULTISTILE / NO VERIFICA ELETTRICA ---')
    print('Impianto:',r['source'].get('plant_id') or 'non specificato')
    for k,v in r['summary'].items():print(k,':',v)
    print('Stato:',r['status'])
    print('Copertura geometrica: CAMPIONATA; controlli elettrici non verificati')
    print('Alpha7: simboli e contatti sono PROPOSTE non verificate; non utilizzare come asset o connessioni')
    print('ATTENZIONE: i rimandi e le regioni vettoriali restano candidati, ZERO percorsi verificati')
    print('JSON:',out,'CSV:',out.with_suffix('.csv'))
    return 0

if __name__=='__main__':raise SystemExit(main())
