"""Alpha18 conservative vector CAD symbol candidates, not SAP hierarchy."""
import argparse
from .sap.vector_semantics_alpha18 import inspect_vector_semantics,write_semantics_outputs

def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha18: candidati inverter CAD, senza generare asset SAP')
    p.add_argument('--pdf',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--max-pages',type=int,default=3)
    a=p.parse_args(argv)
    result,previews=inspect_vector_semantics(a.pdf,max_pages=a.max_pages)
    out=write_semantics_outputs(result,previews,a.out)
    print('[ALPHA18] Candidati grafici di conversione:',len(result['converter_candidates']))
    print('Rami di uscita osservati per candidato:',[i['outgoing_branches_observed'] for i in result['converter_candidates']])
    print('Pannelli grafici inferiori:',len(result['downstream_graphic_panels']))
    print('Output:',out)
    print('Nessun inverter/TR/CU/SB promosso a asset SAP. Verifiche manuali ancora necessarie.')
    return 0

if __name__=='__main__':raise SystemExit(main())
