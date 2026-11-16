"""Alpha7 source-traceable review queue; no claim of electrical verification."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

from .integration.multistyle import audit_multistyle


def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha7: identifica candidati simbolo e contatto; NON verifica elettrica')
    p.add_argument('--pdf',required=True)
    p.add_argument('--plant-id')
    p.add_argument('--max-pages',type=int)
    p.add_argument('--max-probe-pages',type=int,default=3)
    p.add_argument('--regions-per-page',type=int,default=3)
    p.add_argument('--max-drawings',type=int,default=8500)
    p.add_argument('--out-json',default='reports/alpha7_symbol_review.json')
    args=p.parse_args(argv)
    audit=audit_multistyle(args.pdf,plant_id=args.plant_id,max_pages=args.max_pages,
        max_probe_pages=args.max_probe_pages,regions_per_page=args.regions_per_page,
        max_drawings=args.max_drawings)
    review=[]
    for row in audit['pages']:
        for region in row['local_vector_reviews']:
            diag=region.get('alpha7_symbol_terminal',{})
            review.append({
                'page':row['page'],'tag':region['tag'],'tag_type':region['tag_type'],
                'tag_bbox':region['source_bbox'],'roi':region['roi'],
                'status':region['status'],'decision':diag.get('decision','NOT_EVALUATED'),
                'symbol_hypotheses':diag.get('symbol_hypotheses',[]),
                'possible_contacts_unverified':diag.get('possible_contact_points',[]),
                'drawing_note_cues':diag.get('drawing_note_cues',[]),
                'symbol_tag_collision':diag.get('symbol_tag_collision',False),
                'physical_asset_verified':False,'terminals_verified':0,
                'through_device_path_verified':False,
                'feeder_membership_graph_verified':False,
            })
    report={'schema':'sld-alpha7-symbol-review/v1','source':audit['source'],
        'status':audit['status'],'summary':audit['summary'],
        'coverage':{'classified_pages':audit['source']['pages_classified'],
                    'total_pages':audit['source']['page_count'],
                    'pages_probed':audit['summary']['pages_geometry_probe_attempted'],
                    'geometry_is_sampled':True,
                    'note':'Tag-local ROIs, never all symbols or devices in complete pages. Alpha8 has a separate geometry-first command.'},
        'reviews':review,
        'evidence_policy':'Only candidate symbols and contact points. No physical asset, terminal, internal continuity, or feeder path verified.'}
    out=Path(args.out_json);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with out.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['page','tag','tag_type','geometry_status','decision',
            'symbol_hypotheses_unverified','contacts_unverified','note_context','collision',
            'source_circle_drawings','source_stroke_ids','physical_terminals_verified'])
        for item in review:
            w.writerow([item['page'],item['tag'],item['tag_type'],item['status'],item['decision'],
               len(item['symbol_hypotheses']),len(item['possible_contacts_unverified']),
               bool(item['drawing_note_cues']),item['symbol_tag_collision'],
               ','.join(str(a) for h in item['symbol_hypotheses'] for a in h['circle_drawing_ids']),
               ','.join(x['source_stroke_id'] for x in item['possible_contacts_unverified']), 0])
    print('--- ALPHA 7 - SIMBOLI E CONTATTI / SOLO CANDIDATI ---')
    print('Impianto:',args.plant_id or 'non specificato')
    print('Pagine classificate:',report['coverage']['classified_pages'],'/',report['coverage']['total_pages'])
    print('Pagine con geometria analizzata:',report['coverage']['pages_probed'])
    print('Regioni analizzate:',len(review))
    for k in ('alpha7_unique_pair_drawings_unverified','alpha7_possible_edge_contacts_unverified',
              'alpha7_drawing_note_regions','alpha7_symbol_tag_collision_regions','roi_safety_cap_regions',
              'graph_verified_feeder_memberships'):
        print(k,':',report['summary'].get(k,0))
    print('Copertura geometrica:', 'SOLO REGIONI ATTORNO AI TAG (CAMPIONATA)')
    print('ATTENZIONE: nessun terminale o attraversamento elettrico dimostrato')
    print('JSON:',out,'CSV:',out.with_suffix('.csv'))
    return 0

if __name__=='__main__':raise SystemExit(main())
