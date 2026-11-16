"""Operator-auditable, read-only integration of beta2 semantics with beta3 geometry."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from .integration.semantic_bridge import inspect_page, choose_unique_tag_roi

def main():
    a=argparse.ArgumentParser(description='Bootstrap5: integrazione semantica/geometrica (diagnostica, non inferenza di membership)')
    a.add_argument('--pdf',required=True)
    a.add_argument('--page',type=int,default=1)
    a.add_argument('--roi',nargs=4,type=float,metavar=('X0','Y0','X1','Y1'))
    a.add_argument('--max-strokes',type=int,default=1200)
    a.add_argument('--auto-roi-tag',help='Tag testuale univoco da usare per selezionare un ROI diagnostico')
    a.add_argument('--roi-padding',type=float,default=70.0)
    a.add_argument('--feeder-point',nargs=2,type=float,metavar=('X','Y'))
    a.add_argument('--feeder-label')
    a.add_argument('--plant-id')
    a.add_argument('--target-tag')
    a.add_argument('--out',default='reports/semantic_bridge.json')
    args=a.parse_args()
    if args.roi and args.auto_roi_tag:
        a.error('--roi e --auto-roi-tag sono alternativi')
    roi=args.roi
    selection=None
    if args.auto_roi_tag:
        roi,selection=choose_unique_tag_roi(args.pdf,args.page,args.auto_roi_tag,padding=args.roi_padding)
    report=inspect_page(args.pdf,args.page,roi=roi,max_strokes=args.max_strokes,
                        feeder_point=args.feeder_point,feeder_label=args.feeder_label,
                        plant_id=args.plant_id,target_tag=args.target_tag)
    if selection is not None:
        report['automatic_roi_selection']=selection
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(f"{report['status']} | pagina={args.page} | scope={report['scope']}")
    print(f"  evidenze testuali={report['text']['anchor_count']} | simboli candidati={len(report['symbols'])} | grafo={report['geometry']['status']}")
    print(f"  connessioni elettriche feeder verificate={len(report['feeder_graph_verified_membership'])}")
    for t in report['traces']:
        print('  percorso:',t['status'],t.get('target_tag',t.get('reason','')))
    print('Report:',dest)
if __name__=='__main__':main()
