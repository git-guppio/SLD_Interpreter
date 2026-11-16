"""CLI to inspect PDF connectivity independent of beta2 decision pipeline."""
import argparse,json
from .geometry.kernel import analyze_pdf
from .tests.fixture_builder import generate
from pathlib import Path
def main():
    p=argparse.ArgumentParser(description='SLD2Hierarchy beta3 geometry research CLI')
    p.add_argument('--pdf')
    p.add_argument('--page',type=int,default=1)
    p.add_argument('--out')
    p.add_argument('--create-fixtures')
    p.add_argument('--max-strokes',type=int,default=20000)
    args=p.parse_args()
    if args.create_fixtures:
        print(json.dumps(generate(args.create_fixtures),ensure_ascii=False));return
    if not args.pdf:p.error('Specify --pdf or --create-fixtures')
    r=analyze_pdf(args.pdf,page_number=args.page,max_strokes=args.max_strokes)
    if args.out:
        Path(args.out).parent.mkdir(parents=True,exist_ok=True)
        Path(args.out).write_text(json.dumps(r,indent=2),encoding='utf8')
        print(f"{r['status']}: {r['component_count']} components / {r['strokes']} strokes -> {args.out}")
    else:print(json.dumps({k:v for k,v in r.items() if k not in ('components','edges')},indent=2))
if __name__=='__main__':main()
