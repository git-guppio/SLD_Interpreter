"""Alpha12 PDF-first spreadsheet output: CU, TR, local INV, documentary SB count.

No GT input is accepted. XLSX and semicolon CSV are produced together.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .sap.label_first import extract_candidates, write_outputs
from .sap.parentage_alpha11 import propose_parentage, write_proposals
from .sap.stereotypes_alpha12 import build_stereotype_export, write_stereotype_outputs


def main() -> int:
    p=argparse.ArgumentParser(description='Alpha12 SAP stereo: Excel + CSV, no GT, no auto-confirmed electrical paths')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sld', help='Original SLD PDF; derive Alpha10/11 then Alpha12 output')
    mode.add_argument('--alpha10-json', help='Alpha10 existing report, use with --alpha11-json')
    p.add_argument('--alpha11-json', help='Existing Alpha11 proposal file, required with --alpha10-json')
    p.add_argument('--plant-id', help='Required with --sld; optional validation of report plant ID')
    p.add_argument('--review-json',help='Approved plant-scoped HITL review; only with --sld')
    p.add_argument('--out-dir', default='reports/sap_alpha12')
    args=p.parse_args()
    if args.sld and (not args.plant_id or args.alpha11_json):
        p.error('--sld richiede --plant-id e non accetta --alpha11-json')
    if args.alpha10_json and (not args.alpha11_json or args.review_json):
        p.error('--alpha10-json richiede --alpha11-json; la review si applica solo in modalita --sld')
    out=Path(args.out_dir)
    try:
        if args.sld:
            review=json.loads(Path(args.review_json).read_text(encoding='utf-8-sig')) if args.review_json else None
            baseline=extract_candidates(args.sld,args.plant_id,review)
            proposals=propose_parentage(baseline)
            write_outputs(baseline,out)
            write_proposals(proposals,out)
        else:
            baseline=json.loads(Path(args.alpha10_json).read_text(encoding='utf-8-sig'))
            proposals=json.loads(Path(args.alpha11_json).read_text(encoding='utf-8-sig'))
        if args.plant_id:
            wanted=args.plant_id if args.plant_id.startswith('CI::') else 'CI::'+args.plant_id
            if wanted!=baseline.get('plant_id'):
                raise ValueError(f'Impianto richiesto {wanted} != impianto nel report {baseline.get("plant_id")}')
        result=build_stereotype_export(baseline,proposals)
        files=write_stereotype_outputs(result,out)
    except (OSError,ValueError,KeyError,TypeError,IndexError) as ex:
        p.exit(2,f'ERRORE Alpha12: {ex}\n')
    s=result['summary']
    print('--- ALPHA 12 | EXPORT SAP GERARCHIE STEREOTIPATE (STAGING) ---')
    print('Impianto:',result['plant_id'])
    print('CU:',s['cu'],'TR:',s['tr'],'Inverter / righe:',s['inverters'])
    print('TR per CU prevalenti:',s['stereotype_tr_per_cu'] or 'NON DETERMINATO',
          '| uniformi:',s['stereotype_tr_uniform_all_cus'])
    print('INV per TR prevalenti:',s['stereotype_inv_per_tr'] or 'NON DETERMINATO',
          '| uniformi:',s['stereotype_inv_uniform_all_trs'])
    print('String Box documentate:',s['string_box_quantity_total_resolved'],
          '| inverter con quantita irrisolta:',s['string_box_quantities_unresolved'])
    print('Parent TR/INV confermati HITL:',s['tr_inverter_parent_hitl_confirmed'],
          '| proposti/confermati:',s['tr_inverter_parent_candidates_or_confirmed'])
    print('VERDE = cardinalita ricorrente, NON verifica elettrica.')
    print('MATRIX FLOW: tracciato non ancora certificato.')
    for name,path in files.items():print(f'{name}: {path}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
