"""Build real vector PDFs, not mocked graph objects."""
from pathlib import Path
import pymupdf as fitz

def generate(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    cases=['crossing_without_dot','crossing_with_dot','t_junction','short_terminal_segment','colored_conductor','dashed_boundary','device_interposed','short_gap','thick_busbar','diagonal_conductor','segment_limit']
    for name in cases:
        doc=fitz.open()
        p=doc.new_page(width=300,height=220)
        def line(a,b,color=(0,0,0),width=1,dashes=None):
            sh=p.new_shape();sh.draw_line(fitz.Point(*a),fitz.Point(*b))
            sh.finish(color=color,width=width,dashes=dashes)
            sh.commit()
        if name.startswith('crossing'):
            line((30,100),(270,100));line((150,30),(150,190))
            if name=='crossing_with_dot':
                sh=p.new_shape();sh.draw_circle((150,100),2)
                sh.finish(color=(0,0,0),fill=(0,0,0));sh.commit()
        elif name=='t_junction':
            line((30,100),(270,100));line((150,30),(150,100))
        elif name=='short_terminal_segment':
            line((30,100),(147,100));line((147,100),(150,100));line((150,100),(270,100))
        elif name=='colored_conductor':
            line((30,100),(150,100),color=(0,0,1));line((150,100),(270,100),color=(0,0,1))
        elif name=='dashed_boundary':
            line((30,100),(270,100));line((150,30),(150,190),dashes='[4 4] 0')
        elif name=='device_interposed':
            line((30,100),(140,100));line((160,100),(270,100))
            sh=p.new_shape();sh.draw_rect(fitz.Rect(140,90,160,110));sh.finish(color=(0,0,0));sh.commit()
        elif name=='short_gap':
            line((30,100),(148,100));line((150,100),(270,100))
        elif name=='thick_busbar':
            line((30,100),(270,100),width=5);line((150,100),(150,180))
        elif name=='diagonal_conductor':
            line((30,30),(150,100));line((150,100),(270,180))
        elif name=='segment_limit':
            for i in range(6):line((30,25+i*25),(270,25+i*25))
        path=root/f'{name}.pdf';doc.save(str(path),garbage=4,deflate=True);doc.close()
    return cases
