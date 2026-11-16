"""Alpha16 CLI: native LVL-SB/INV diagram labels, conservative staging."""
from __future__ import annotations
import argparse
from pathlib import Path
from .sap.lvl_indexed_alpha16 import extract_lvl_indexed,write_outputs

def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha16: native-indexed inverter/string-box labels, geometric TR candidates')
    p.add_argument('--pdf',required=True)
    p.add_argument('--plant-id',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args(argv)
    result=extract_lvl_indexed(a.pdf,a.plant_id)
    write_outputs(result,a.out)
    s=result['summary']
    print('--- Alpha16 LVL-SB -> INV ---')
    print('CU',s['cu'],'TR CANDIDATI',s['tr_candidate'],'INV',s['inverters'])
    print('INV con SB quantificate',s['box_quantities_complete'],'su',s['inverters'])
    print('String Box da etichette',s['box_quantity_total_complete_only'])
    print('Parent TR candidati',s['parent_candidates'],'| verificati elettricamente 0')
    print('Output',Path(a.out).resolve())
    print('STAGING: Non certificato Matrix FLOW')
    return 0

if __name__=='__main__':raise SystemExit(main())
