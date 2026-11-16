"""Alpha19 vector-document conservative graphic correlations."""
from __future__ import annotations
import argparse
from .sap.vector_relations_alpha19 import inspect_cad_relations,write_cad_relation_outputs


def main(argv=None):
    parser=argparse.ArgumentParser(description='Ipotesi grafiche CAD (non gerarchia SAP confermata)')
    parser.add_argument('--pdf',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--max-pages',type=int,default=3)
    args=parser.parse_args(argv)
    base,previews,report=inspect_cad_relations(args.pdf,max_pages=args.max_pages)
    dest=write_cad_relation_outputs(base,previews,report,args.out)
    s=report['summary']
    print(f"ALPHA19 candidati inverter-like={s['inverter_like_candidates']} | "
          f"campi grafici={s['fields_detected']} | ipotesi ordinali={s['non_electrical_spatial_proposals']}")
    print('CU, TR, String Box: NON VERIFICATI. Nessuna associazione elettrica automatica.')
    print('Report:',dest)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
