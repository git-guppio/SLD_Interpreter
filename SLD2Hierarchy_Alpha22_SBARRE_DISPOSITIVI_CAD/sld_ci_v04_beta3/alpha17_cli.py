"""Alpha17 command-line triage of textless CAD/vector PDF SLDs."""
import argparse
from .sap.vector_diagnostics_alpha17 import inspect_vector_pdf, write_vector_outputs


def main():
    parser=argparse.ArgumentParser(description='Diagnostica geometrica: NON genera asset SAP')
    parser.add_argument('--pdf',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--compare-pdf',default=None)
    parser.add_argument('--max-pages',type=int,default=3)
    opts=parser.parse_args()
    result,previews=inspect_vector_pdf(opts.pdf,compare_pdf=opts.compare_pdf,max_pages=opts.max_pages)
    output=write_vector_outputs(result,previews,opts.out)
    print('[ALPHA17] Diagnostica CAD/vettoriale completata:',output)
    print('Pagine analizzate:',result['pages_sampled'],'gruppi grafici ripetuti:',len(result['geometric_repeat_groups']))
    print('CU/TR/INV/SB verificati: NON RISOLTI (non zero). Nessuna gerarchia SAP inventata.')
    if 'cross_document_comparison' in result:
        print('Confronto grafico:',result['cross_document_comparison'])
    return 0


if __name__=='__main__':raise SystemExit(main())
