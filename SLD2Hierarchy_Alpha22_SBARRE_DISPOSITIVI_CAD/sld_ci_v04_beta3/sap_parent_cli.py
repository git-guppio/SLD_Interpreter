"""Alpha11 independent parent proposals, optional explicit HITL confirmation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .sap.label_first import extract_candidates,write_outputs
from .sap.parentage_alpha11 import propose_parentage,write_proposals


def main():
    p=argparse.ArgumentParser(description='Alpha11: conservative TR/inverter SAP candidate mapping (no GT)')
    p.add_argument('--sld',required=True)
    p.add_argument('--plant-id',required=True)
    p.add_argument('--review-json',help='HITL explicit, never generated automatically from suggestions')
    p.add_argument('--out-dir',default='reports/sap_alpha11')
    args=p.parse_args()
    try:
        review=json.loads(Path(args.review_json).read_text(encoding='utf-8-sig')) if args.review_json else None
        baseline=extract_candidates(args.sld,args.plant_id,review)
        out=Path(args.out_dir)
        write_outputs(baseline,out)  # alpha10 backward compatible in a separate destination
        prop=propose_parentage(baseline)
        write_proposals(prop,out)
    except (OSError,ValueError,KeyError) as ex:
        p.exit(2,f'ERRORE: {ex}\n')
    s=prop['summary']
    print('--- ALPHA 11 | RELAZIONI TR -> INVERTER, SOLO PROPOSTE GEOMETRICHE ---')
    print('Impianto:',prop['plant_id'])
    print('CU identificate:',baseline['summary']['cu_labels'])
    print('TR candidati:',baseline['summary']['transformer_label_candidates'])
    print('Inverter candidati:',s['inverters_total'])
    print('Associazioni TR->INV candidate:',s['spatial_parent_candidates'])
    print('Inverter senza proposta:',s['spatial_parent_unresolved'])
    print('Parent confermati da operatore:',s['inverters_already_confirmed'])
    print('Gruppi HITL proposti:',len(prop['suggested_hitl_groups']))
    print('VERIFICA ELETTRICA:',s['electrical_paths_verified'],'percorsi. Nessun parent promosso automaticamente.')
    print('Report in:',out)
    return 0

if __name__=='__main__':raise SystemExit(main())
