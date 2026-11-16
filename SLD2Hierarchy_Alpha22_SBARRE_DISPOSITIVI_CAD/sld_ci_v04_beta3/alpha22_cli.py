"""Alpha22 CAD CLI: Alpha21 SAP provenance plus source-segment busbar audit."""
import argparse
import json
from pathlib import Path
from .sap.cad_conductor_graph_alpha20 import inspect_cad_conductor_runs, write_cad_conductor_outputs
from .sap.cad_qps_hierarchy_alpha21 import build_alpha21_hierarchy, write_alpha21_outputs
from .sap.cad_bus_provenance_alpha22 import audit_cad_pdf, write_alpha22_reports
from .sap.cad_thresholds import CadBusThresholds


def main(argv=None):
    p=argparse.ArgumentParser(description='Alpha22: source evidence of common busbars and unresolved protection-device gaps')
    p.add_argument('--pdf',required=True);p.add_argument('--plant-id',required=True)
    p.add_argument('--out',required=True);p.add_argument('--review-json')
    p.add_argument('--no-local-ocr',action='store_true');p.add_argument('--tesseract')
    p.add_argument('--max-pages',type=int,default=3)
    p.add_argument('--soglie',help='Profilo JSON di soglie CAD (default: valori tarati su Settimo/PV3)')
    a=p.parse_args(argv)
    plant=a.plant_id if a.plant_id.startswith('CI::') else 'CI::'+a.plant_id
    try:
        thresholds=CadBusThresholds.load(a.soglie)
        base,previews,prior,report20=inspect_cad_conductor_runs(
            a.pdf,a.max_pages,local_ocr=not a.no_local_ocr,tesseract_executable=a.tesseract)
        review=json.loads(Path(a.review_json).read_text(encoding='utf-8-sig')) if a.review_json else None
        result,export=build_alpha21_hierarchy(a.pdf,plant,report20,prior,base['converter_candidates'],review)
        topological=audit_cad_pdf(a.pdf,report20,thresholds)
        # Validate operator input before touching the output directory.
        write_cad_conductor_outputs(base,previews,prior,report20,a.out)
        paths21=write_alpha21_outputs(result,export,a.out)
        paths22=write_alpha22_reports(a.pdf,topological,a.out)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        p.exit(2,f'[ERRORE Alpha22] {exc}\n')
    print('ALPHA22: grafi documentali e discontinuita attraverso apparecchiature')
    print('Gerarchia QPS:',result['summary'])
    print('Sbarre e discontinuita:',topological['summary'])
    for name,path in {**paths21,**paths22}.items():print('  ',name,':',path)
    print('Connessioni complete automatiche TR->INV: 0. Nessuna discontinuita e stata attraversata per supposizione.')
    return 0

if __name__=='__main__':raise SystemExit(main())
