"""CLI: coordinate-anchored geometric trace with auditable source stroke IDs."""
import argparse,json
from pathlib import Path
from .geometry.path_trace import query_pdf

def main():
    p=argparse.ArgumentParser(description='Beta3 trace di geometria vettoriale (non inferenza feeder)')
    p.add_argument('--pdf',required=True)
    p.add_argument('--page',type=int,default=1)
    p.add_argument('--start',type=float,nargs=2,required=True,metavar=('X','Y'))
    p.add_argument('--end',type=float,nargs=2,required=True,metavar=('X','Y'))
    p.add_argument('--roi',type=float,nargs=4)
    p.add_argument('--max-strokes',type=int,default=1200)
    p.add_argument('--out',default='reports/path_query.json')
    args=p.parse_args()
    if args.max_strokes<1:p.error('max-strokes deve essere positivo')
    if args.roi and (args.roi[0]>=args.roi[2] or args.roi[1]>=args.roi[3]):p.error('ROI non valido')
    r=query_pdf(args.pdf,args.page,args.start,args.end,roi=args.roi,max_strokes=args.max_strokes)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
    print(f"{r['status']} | scope={r['scope']} | tratti={r['inventory']['retained']} | grafo={r['graph']['status']}")
    print('Output:',out)
if __name__=='__main__':main()
