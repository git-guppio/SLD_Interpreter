"""Command-line entrypoint for alpha15 multistyle native-label recognition."""
from __future__ import annotations
import argparse
from pathlib import Path
from .sap.multistyle_alpha15 import extract_indexed_families,write_csv_outputs

def main(argv=None):
    parser=argparse.ArgumentParser(description='Alpha 15: diagnostica documentale multistile, non import SAP validato')
    parser.add_argument('--pdf',required=True)
    parser.add_argument('--plant-id',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    r=extract_indexed_families(args.pdf,args.plant_id)
    write_csv_outputs(r,args.out)
    s=r['summary'];print('--- Alpha 15: identificativi CAD e sequenze String Box ---')
    print('Impianto:',r['plant_id'])
    print('CU:',s['cu'],'| TR candidati:',s['tr_candidate'],'| INV:',s['inverters'])
    print('Quantita SB complete:',s['box_quantities_complete'],'| non risolte:',s['box_quantities_unresolved'])
    print('Somma SB risolte:',s['box_quantity_total_complete_only'])
    print('Associazioni TR->INV candidate:',s['parent_candidates'],'| confermate:',s['parent_confirmed'])
    print('Report:',Path(args.out).resolve())
    print('NOTA: regole non validate su ground truth indipendente; no Matrix FLOW import.')
    return 0

if __name__=='__main__':raise SystemExit(main())
