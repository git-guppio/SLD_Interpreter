"""Alpha21 CAD QPS source enumeration and operator-confirmed SAP hierarchy."""
import argparse
import json
from pathlib import Path
from .sap.cad_conductor_graph_alpha20 import inspect_cad_conductor_runs, write_cad_conductor_outputs
from .sap.cad_qps_hierarchy_alpha21 import build_alpha21_hierarchy,write_alpha21_outputs


def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha21 QPS = String Box with source-grounded OCR and scoped review')
    p.add_argument('--pdf',required=True);p.add_argument('--plant-id',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--review-json',help='Review con dichiarazioni tecniche, hash PDF e appartenenze CU/TR/INV')
    p.add_argument('--no-local-ocr',action='store_true')
    p.add_argument('--tesseract',default=None)
    p.add_argument('--max-pages',type=int,default=3)
    args=p.parse_args(argv)
    plant=args.plant_id if args.plant_id.startswith('CI::') else 'CI::'+args.plant_id
    try:
        base,preview,prior,report20=inspect_cad_conductor_runs(args.pdf,args.max_pages,
                    local_ocr=not args.no_local_ocr,tesseract_executable=args.tesseract)
        review=json.loads(Path(args.review_json).read_text(encoding='utf-8-sig')) if args.review_json else None
        result,export=build_alpha21_hierarchy(args.pdf,plant,report20,prior,
                                              base['converter_candidates'],review)
        # All review checks happen before we write report files.
        write_cad_conductor_outputs(base,preview,prior,report20,args.out)
        files=write_alpha21_outputs(result,export,args.out)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        p.exit(2,f'[ERRORE Alpha21] {exc}\n')
    print('ALPHA21: CAD QPS / String Box, fonte PDF separata da conferme operatore')
    print('Riepilogo:',result['summary'])
    for name,path in files.items():print(f'  {name}: {path}')
    if not export:print('Nessuna review: parent CU/TR e conteggio SAP non vengono dichiarati risolti.')
    else:print('Gerarchia CU/TR confermata dall operatore; continuita elettrica automatica NON verificata.')
    return 0

if __name__=='__main__':raise SystemExit(main())
