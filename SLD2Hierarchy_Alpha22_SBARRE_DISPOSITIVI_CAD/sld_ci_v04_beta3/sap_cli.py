"""Alpha9 SAP hierarchy PoC: from complete dev14c inference or source PDFs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .sap.hierarchy_export import build_sap_hierarchy, save_sap_outputs


def main() -> int:
    p=argparse.ArgumentParser(description='Alpha9: hierarchy SAP staging; no full electrical graph validation')
    src=p.add_mutually_exclusive_group(required=True)
    src.add_argument('--inference-json',help='Full prior dev14c_inference.json (not concise integrated_report)')
    src.add_argument('--sld',help='Original SLD PDF for new dev14c inference')
    p.add_argument('--layout',help='Optional layout PDF; only with --sld')
    p.add_argument('--plant-id',help='Plant identifier for new source inference')
    p.add_argument('--ocr-mode',choices=['never','auto','always'],default='auto')
    p.add_argument('--review-json',help='Optional explicitly confirmed plant-scoped SAP assets/links')
    p.add_argument('--out-dir',default='reports/sap_alpha9')
    args=p.parse_args()
    if args.layout and not args.sld:
        p.error('--layout richiede --sld')
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    if args.inference_json:
        source_path=Path(args.inference_json)
        source=json.loads(source_path.read_text(encoding='utf-8-sig'))
    else:
        from sld_ci_v04_beta2_dev14c.cli import run_case
        from sld_ci_v04_beta2_dev14c.config import RunConfig
        if not Path(args.sld).is_file():
            p.error(f'File SLD non trovato: {args.sld}')
        print('Avvio inferenza documentale esistente; puo richiedere diversi minuti...')
        source=run_case(args.sld, str(out/'dev14c_inference.json'),
                        RunConfig(ocr_mode=args.ocr_mode),
                        layout_path=args.layout,plant_id=args.plant_id)
    if args.plant_id and args.inference_json:
        got=str((source.get('plant') or {}).get('plant_id',''))
        normalized=args.plant_id if args.plant_id.startswith('CI::') else 'CI::'+args.plant_id
        if got!=normalized:
            p.error(f'Impianto richiesto {normalized} non corrisponde alla fonte {got}')
    review=json.loads(Path(args.review_json).read_text(encoding='utf-8-sig')) if args.review_json else None
    result=build_sap_hierarchy(source,review)
    files=save_sap_outputs(result,out)
    print('\n--- ALPHA 9 | GERARCHIA SAP - NON ANCORA MATRIX FLOW DIRETTO ---')
    print('Impianto:',result['plant_id'])
    print('Stato:',result['status'])
    print('CU identificate:',result['plant_summary']['identified_cu_count'])
    print('Dispositivi riconciliati:',result['plant_summary']['counts_resolved_by_type'])
    print('Questioni HITL:',len(result['hitl_tasks']))
    print('Raggruppamento HITL:',result['hitl_groups'])
    print('Feeder non richiesti. Nessun asset mancante creato automaticamente.')
    print('ATTENZIONE: csv di STAGING; tracciato Matrix Flow definitivo non ancora verificato.')
    print('File:',*files,sep='\n  ')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
