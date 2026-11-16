"""Alpha20 CAD input conductor diagnostics."""
import argparse
from .sap.cad_conductor_graph_alpha20 import inspect_cad_conductor_runs,write_cad_conductor_outputs

def main(argv=None):
    p=argparse.ArgumentParser(description='Tracciamento CAD conduttori in ingresso inverter')
    p.add_argument('--pdf',required=True);p.add_argument('--out',required=True)
    p.add_argument('--max-pages',type=int,default=3)
    p.add_argument('--no-local-ocr',action='store_true',help='Disattiva OCR locale facoltativo')
    p.add_argument('--tesseract',default=None,help='Percorso a tesseract.exe offline')
    args=p.parse_args(argv)
    base,preview,prior,result=inspect_cad_conductor_runs(args.pdf,args.max_pages,local_ocr=not args.no_local_ocr,
                                               tesseract_executable=args.tesseract)
    out=write_cad_conductor_outputs(base,preview,prior,result,args.out)
    print('ALPHA20 - conduzione fino a morsetto aperto, NON parent TR validato')
    print(result['summary']);print('Report in',out)
    return 0
if __name__=='__main__':raise SystemExit(main())
