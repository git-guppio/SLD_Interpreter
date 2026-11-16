"""Single, end-to-end diagnostic run. Legacy inference never receives GT."""
from __future__ import annotations
import argparse
from .integration.integrated_case import run_integrated

def main():
    p=argparse.ArgumentParser(description='Beta3 integrated SLD + optional layout, read-only input')
    p.add_argument('--sld',required=True,help='Complete primary electrical PDF')
    p.add_argument('--layout',help='Optional layout PDF')
    p.add_argument('--plant-id',help='Explicit plant ID when SLD/layout names differ')
    p.add_argument('--out-dir',default='reports/integrated_run',help='Separate output directory')
    p.add_argument('--max-pages',type=int,default=None,help='DIAGNOSTIC ONLY: limit processed pages')
    p.add_argument('--max-pairs',type=int,default=4)
    p.add_argument('--max-neighborhoods',type=int,default=3)
    p.add_argument('--max-strokes',type=int,default=1200)
    p.add_argument('--geometry-first-pages',type=int,default=0,help='Alpha8 diagnostic: scan this many PDF pages for vector shapes independently of native text; 0 disables')
    p.add_argument('--ocr-mode',choices=['never','auto','always'],default='auto')
    p.add_argument('--baseline-json',default=None,help='Reuse an existing dev14c inference; source name, plant and page count checked; PDF bytes not authenticated')
    p.add_argument('--knowledge-store',default=None,help='Optional explicit plant learning JSON')
    p.add_argument('--operator-feedback',default=None)
    args=p.parse_args()
    r=run_integrated(args.sld,args.out_dir,layout_path=args.layout,
        plant_id=args.plant_id,max_pages=args.max_pages,
        max_pairs=args.max_pairs,max_strokes=args.max_strokes,
        max_neighborhoods=args.max_neighborhoods,
        geometry_first_pages=args.geometry_first_pages,
        ocr_mode=args.ocr_mode,knowledge_path=args.knowledge_store,
        operator_feedback_path=args.operator_feedback,
        baseline_json_path=args.baseline_json)
    l=r['legacy_inference'];b=r['beta3_geometry']['summary']
    print('\n--- RISULTATO INTEGRATO ---')
    print('Stato:',r['status'],'| impianto:',r['plant_id'])
    if r['baseline_reuse']['reused']:
        print('NOTA: baseline dev14c RIUTILIZZATA, non nuova inferenza; fonte verificata solo per nome e pagine')
    print('Asset risolti (dev14c):',l['target_counts'])
    m=l['membership_provenance']
    print('CU assegnate a feeder (riconciliazione dev14c):',m['canonical_cu_feeder_membership_count'])
    print('Di cui assegnazioni strutturali INFERRED:',m['structural_inferred_count'])
    print('Membership ricavate da schedule espliciti:',m['explicit_schedule_membership_count'])
    print('Membership verificate dal grafo (dev14c):',l['legacy_graph_verification']['summary_count'])
    print('Fused symbols con terminali (beta2):',b['named_fused_symbol_count'])
    print('Coda CU da verificare elettricamente:',b['cu_identity_tasks'])
    print('Aree SLD studiate intorno a CU:',b['cu_neighborhoods_inspected'])
    print('Coppie FUSED studiate (beta3):',b['inspections_completed'])
    print('Percorsi geometrici locali candidati:',b['local_geometric_path_candidates'])
    print('Tracciamenti feeder beta3 verificati:',b['beta3_graph_verified_feeder_membership'])
    xs=r['beta3_cross_sheet_references']['summary']
    comp=r['beta3_cross_sheet_references']['independent_layout_comparison']
    print('Rimandi tra fogli reciproci (SOLO DOCUMENTALI):',xs['reciprocal_documentary_links'])
    print('Gruppi da rimandi tra fogli (NON feeder verificati):',xs['cross_sheet_groups'])
    print('Rimandi concordanti con il layout:',comp['same_layout_feeder'],'/',comp['comparable_links'])
    k=r['operator_knowledge_audit']
    print('Knowledge store PLANT:',k['included_patterns'],'regole applicabili,', k['excluded_patterns'],'escluse')
    preflight=r.get('beta3_multistyle_preflight',{}).get('summary',{})
    print('Alpha5 - pagine con apparecchiature nominate:',preflight.get('pages_with_named_equipment',0))
    print('Alpha5 - pagine MATCHLINE:',preflight.get('pages_with_matchline',0))
    print('Alpha5 - pagine senza testo nativo:',preflight.get('pages_without_native_text',0))
    print('Alpha5 - regioni geometriche di revisione:',preflight.get('local_vector_review_regions',0))
    print('Alpha7 - simboli a due anelli candidati:',preflight.get('alpha7_paired_circle_symbol_candidates',0))
    print('Alpha7 - contatti geometrici candidati, NON terminali:',preflight.get('alpha7_possible_edge_contacts_unverified',0))
    print('Alpha8 - pagine scansionate direttamente dai vettori:',preflight.get('alpha8_geometry_first_pages_attempted',0))
    print('Alpha8 - ipotesi geometriche NON asset:',preflight.get('alpha8_geometry_first_hypotheses_unverified',0))
    print('NOTA: diagnostica Alpha7/8, zero verifica elettrica aggiuntiva')
    print('File:',args.out_dir+'/integrated_report.json')
if __name__=='__main__':main()
