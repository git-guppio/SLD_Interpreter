"""Independent validation executable; never part of SLD inference."""
import argparse
from .sap.parent_reference_alpha11 import compare_parents

def main():
    p=argparse.ArgumentParser(description='Alpha11 post-inference compare against separate operator GT')
    p.add_argument('--proposals-json',required=True)
    p.add_argument('--reference-txt',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    s=compare_parents(a.proposals_json,a.reference_txt,a.out)
    print('Parent TR->INV matching:',s['matches'],'/',s['total_comparison_rows'])
    print('Mismatches:',len(s['mismatches']),'| result CSV:',a.out)
    return 0
if __name__=='__main__':raise SystemExit(main())
