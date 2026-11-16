"""Alpha8 combined tag-first and independent vector-first inspection CLI."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from .integration.multistyle import audit_multistyle


def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha8: recognition candidates with and without text; no electrical proof')
    p.add_argument('--pdf',required=True)
    p.add_argument('--plant-id')
    p.add_argument('--max-pages',type=int)
    p.add_argument('--max-probe-pages',type=int,default=4)
    p.add_argument('--regions-per-page',type=int,default=3)
    p.add_argument('--geometry-first-pages',type=int,default=4)
    p.add_argument('--max-shape-groups',type=int,default=30)
    p.add_argument('--out-json',default='reports/alpha8_geometry_first.json')
    args=p.parse_args(argv)
    if args.geometry_first_pages<0: p.error('geometry-first-pages must be nonnegative')
    r=audit_multistyle(args.pdf,plant_id=args.plant_id,max_pages=args.max_pages,
       max_probe_pages=args.max_probe_pages,regions_per_page=args.regions_per_page,
       geometry_first_pages=args.geometry_first_pages,
       geometry_first_max_groups=args.max_shape_groups)
    coverage={
        'classification_pages':r['source']['pages_classified'],
        'total_document_pages':r['source']['page_count'],
        'geometry_first_pages_scanned':r['summary']['alpha8_geometry_first_pages_attempted'],
        'geometry_first_pages_not_scanned':r['summary']['alpha8_geometry_first_pages_skipped_budget'],
        'geometry_first_source_scans_complete':sum(row['geometry_first'].get('source_scan_complete',False) for row in r['pages']),
        'geometry_first_review_hypotheses_unverified':r['summary']['alpha8_geometry_first_hypotheses_unverified'],
        'tag_first_roi_reviews':r['summary']['local_vector_review_regions'],
        'tag_first_page_sampling_skips':r['summary']['pages_geometry_probe_skipped_by_sampling_budget'],
        'geometry_first_review_groups_omitted':r['summary']['alpha8_geometry_first_unreported_groups'],
        'full_equipment_coverage_claimed':False,
        'physical_assets_verified':0,'physical_terminals_verified':0,'graph_verified_memberships':0,
        'note':'Page-wide SHAPE source scanning is not complete symbol/equipment classification. Both pathways are candidates only.'}
    out=Path(args.out_json);out.parent.mkdir(parents=True,exist_ok=True)
    export={'schema':'sld-beta3-alpha8-dual-path/v1','source':r['source'],'coverage':coverage,
        'page_reports':[{k:v for k,v in row.items() if k in ('page','modes','native_text_lines','geometry_status','geometry_first','named_devices','local_vector_reviews')}
                     for row in r['pages']],
        'unlabeled_shape_review_queue':r['alpha8_geometry_first_review_queue'],
        'tag_first_review_queue':r['alpha7_symbol_review_queue'],
        'evidence_policy':r['evidence_policy']}
    out.write_text(json.dumps(export,ensure_ascii=False,indent=2),encoding='utf-8')
    with out.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['page','native_text_lines','tag_mentions','tag_roi_status','tag_roi_count',
                    'geometry_first_status','vector_drawings','circles_detected','shape_groups_candidate',
                    'groups_omitted','shape_source_scan_complete','verified_equipment','verified_terminals','verified_paths'])
        for row in r['pages']:
            g=row['geometry_first']
            w.writerow([row['page'],row['native_text_lines'],len(row['named_devices']),row['geometry_status'],
                len(row['local_vector_reviews']),g['status'],g.get('drawing_count',''),g.get('circles_detected',''),
                len(g['hypotheses']),g.get('omitted_hypotheses',''),g['source_scan_complete'],0,0,0])
    print('--- ALPHA 8 - DOPPIO PERCORSO: TESTO E GEOMETRIA ---')
    print('Impianto:',args.plant_id or 'non specificato')
    print('Pagine classificate:',coverage['classification_pages'],'/',coverage['total_document_pages'])
    print('Pagine scansione geometrica indipendente:',coverage['geometry_first_pages_scanned'])
    print('Scansioni geometriche fonte complete:',coverage['geometry_first_source_scans_complete'])
    print('Pagine non scansionate geometricamente:',coverage['geometry_first_pages_not_scanned'])
    print('Gruppi di forme circolari candidati (NON asset):',coverage['geometry_first_review_hypotheses_unverified'])
    print('Gruppi omessi per limite report:',coverage['geometry_first_review_groups_omitted'])
    print('Regioni attorno ai tag (Alpha7):',coverage['tag_first_roi_reviews'])
    print('Terminali elettrici verificati: 0; percorsi feeder-CU verificati: 0')
    print('ATTENZIONE: la scansione delle forme NON certifica apparecchiature, terminali o continuita.')
    print('JSON:',out,'CSV:',out.with_suffix('.csv'))
    return 0

if __name__=='__main__':raise SystemExit(main())
