"""Optional post-inference comparison. Never loads GT into detection."""
from __future__ import annotations
import argparse
from .sap.reference_validation import compare_pampa_format

def main():
    p=argparse.ArgumentParser(description='Independent post-inference comparison (Pampa TXT format)')
    p.add_argument('--report',required=True)
    p.add_argument('--reference-txt',required=True)
    p.add_argument('--out',default='reports/sap_alpha10/independent_comparison.csv')
    args=p.parse_args()
    r=compare_pampa_format(args.report,args.reference_txt,args.out)
    print('--- CONFRONTO INDIPENDENTE POST-INFERENZA ---')
    print('Righe: GT',r['reference_rows'],'PDF',r['pdf_rows'])
    print('String Box: GT',r['reference_total_sb'],'PDF',r['pdf_total_sb'])
    print('Corretti per inverter:',r['per_inverter_matching'],'/',r['per_inverter_total'])
    print('Scostamenti (CU, INV, GT, PDF):',r['mismatches'][:30])
    print('Dettaglio CSV:',args.out)
    return 0

if __name__=='__main__':raise SystemExit(main())
