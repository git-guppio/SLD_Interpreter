"""Alpha10 label and geometry anchored SAP-first PDF inspection."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from .sap.label_first import extract_candidates,write_outputs


def main():
    p=argparse.ArgumentParser(description='Alpha10: SAP-first positional label candidate analysis, no GT input')
    p.add_argument('--sld',required=True)
    p.add_argument('--plant-id',required=True)
    p.add_argument('--review-json')
    p.add_argument('--out-dir',default='reports/sap_alpha10')
    args=p.parse_args()
    try:
        review=json.loads(Path(args.review_json).read_text(encoding='utf-8-sig')) if args.review_json else None
        result=extract_candidates(args.sld,args.plant_id,review)
        out=write_outputs(result,args.out_dir)
    except (OSError,ValueError,KeyError) as ex:
        p.exit(2,f'ERRORE: {ex}\n')
    print('--- ALPHA 10 | RICERCA GERARCHIA SAP - SOLO EVIDENZE DOCUMENTALI ---')
    print('Impianto:',result['plant_id'],'| Stato:',result['status'])
    print('Pagine:',len(result['source_pages']))
    print('Etichette CU:',result['summary']['cu_labels'])
    print('Trasformatori candidati:',result['summary']['transformer_label_candidates'])
    print('Inverter candidati:',result['summary']['inverter_label_candidates'])
    print('Etichette quantita String Box abbinate:',result['summary']['string_box_quantity_labels_matched'])
    print('String Box indicate documentalmente:',result['summary']['string_boxes_documentary_quantity_matched'])
    print('Inverter senza padre TR confermato:',result['summary']['unconfirmed_inverter_transformer_parents'])
    print('Anomalie e verifiche HITL:',result['summary']['issues'])
    print('AVVERTENZA: no GT usata, no terminali o continuita elettrica dimostrati.')
    print('Output in',out)
    return 0

if __name__=='__main__':raise SystemExit(main())
