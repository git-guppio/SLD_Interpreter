"""Alpha17 read-only triage for CAD/vector SLDs whose labels lack native PDF text.

Repeated colored CAD drawing regions are *untyped geometric candidates*, not
inverters, transformers or verified electrical links. Ground-truth inventories
are neither read nor consulted. Uses only local PDF and raster processing.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, deque
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError as exc:
    raise ImportError('Per la diagnostica geometrica serve Pillow (pip install pillow).') from exc


COLORS = {'ciano': '#008b9c', 'rosso': '#c23a42', 'verde': '#26885a',
          'blu': '#3f67bc', 'magenta': '#a34a98'}


def vector_only_document(pdf_path, *, sampled_pages=3):
    """Return True only for real drawing-bearing pages without native words."""
    with fitz.open(str(pdf_path)) as pdf:
        pages = min(len(pdf), sampled_pages)
        if pages == 0:
            return False
        return (all(len(pdf[i].get_text('words')) == 0 for i in range(pages))
                and any(len(pdf[i].get_drawings()) >= 7 for i in range(pages)))


def _render(page, width=1000):
    ratio = min(1.0, width / max(page.rect.width, page.rect.height))
    pix = page.get_pixmap(matrix=fitz.Matrix(ratio, ratio), alpha=False)
    return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)


def _mask_color(image, kind):
    """CAD palette filter, robust to anti-aliasing; classification is not semantic."""
    rgb = image.convert('RGB')
    w,h = rgb.size
    pixels = rgb.load()
    mask=Image.new('L',(w,h),0)
    dst=mask.load()
    for y in range(h):
        for x in range(w):
            r,g,b=pixels[x,y]
            if kind=='ciano': flag = g>r+22 and b>r+22 and abs(g-b)<65
            elif kind=='rosso': flag = r>g+25 and r>b+25
            elif kind=='verde': flag = g>r+25 and g>b+25
            elif kind=='blu': flag = b>r+25 and b>g+25
            else: flag = r>g+25 and b>g+25
            if flag:dst[x,y]=255
    return mask


def _components(mask, *, closing=5, min_area=45, min_wh=11):
    # Dashes often need closing. Filter and record underlying pixels so a
    # broad line does not become a high-confidence grouped object by itself.
    after = mask.filter(ImageFilter.MaxFilter(closing)).filter(ImageFilter.MinFilter(closing))
    w,h = after.size
    raw=after.tobytes(); visited=bytearray(w*h)
    result=[]
    for i,val in enumerate(raw):
        if val==0 or visited[i]:continue
        stack=[i]; visited[i]=1
        left=right=i%w; top=bottom=i//w;area=0
        while stack:
            pos=stack.pop();area+=1
            x,y=pos%w,pos//w
            if x<left:left=x
            if x>right:right=x
            if y<top:top=y
            if y>bottom:bottom=y
            if x>0:
                q=pos-1
                if raw[q] and not visited[q]:visited[q]=1;stack.append(q)
            if x<w-1:
                q=pos+1
                if raw[q] and not visited[q]:visited[q]=1;stack.append(q)
            if y>0:
                q=pos-w
                if raw[q] and not visited[q]:visited[q]=1;stack.append(q)
            if y<h-1:
                q=pos+w
                if raw[q] and not visited[q]:visited[q]=1;stack.append(q)
        bw=right-left+1;bh=bottom-top+1
        if area>=min_area and bw>=min_wh and bh>=min_wh and bw<w*.6 and bh<h*.6:
            result.append({'box':[left,top,right+1,bottom+1], 'pixels':area,
                           'width':bw,'height':bh})
    return result


def _group_repeat_shapes(components, *, min_repeats=2):
    """Bucket approximate widths/heights; do not interpret as device symbols."""
    groups=[]
    for c in sorted(components,key=lambda z:(-z['pixels'],z['box'][1],z['box'][0])):
        fits=[]
        for g in groups:
            w,h=g['width'],g['height']
            if abs(c['width']-w) <= max(3, .07*w) and abs(c['height']-h) <= max(3,.07*h):
                fits.append(g)
        if fits:
            # deterministic selection for close-sized motifs
            g=min(fits,key=lambda x:abs(x['width']-c['width'])+abs(x['height']-c['height']))
            g['items'].append(c)
        else:groups.append({'width':c['width'],'height':c['height'],'items':[c]})
    return [g for g in groups if len(g['items'])>=min_repeats]


def _compare_rasters(pdf_path, other_path):
    with fitz.open(str(pdf_path)) as a, fitz.open(str(other_path)) as b:
        if not a or not b:return {'available':False,'reason':'PDF_EMPTY'}
        p,q=a[0],b[0]
        if (abs(p.rect.width/q.rect.width-1)>.01 or abs(p.rect.height/q.rect.height-1)>.01):
            return {'available':False,'reason':'DIFFERENT_PAGE_DIMENSIONS'}
        aa,bb=_render(p,1000),_render(q,1000)
        if aa.size!=bb.size:return {'available':False,'reason':'DIFFERENT_RENDER_DIMENSIONS'}
        ab,ba=aa.tobytes(),bb.tobytes()
        pix=len(ab)//3
        same=sum(max(abs(ab[i]-ba[i]),abs(ab[i+1]-ba[i+1]),abs(ab[i+2]-ba[i+2]))<10
                 for i in range(0,len(ab),3))
        return {'available':True,'sample':'page_1_rgb_render_1000px',
                'approx_equal_pixel_fraction':round(same/pix,6),
                'near_duplicate_candidate':same/pix>0.975,
                'warning':'Somiglianza grafica a bassa risoluzione; non prova identita degli impianti'}


def inspect_vector_pdf(pdf_path, *, compare_pdf=None, max_pages=3):
    pdf=Path(pdf_path)
    if not pdf.is_file():raise FileNotFoundError(pdf)
    pages=[]; all_groups=[]; previews=[]
    with fitz.open(str(pdf)) as doc:
        if len(doc)<1:raise ValueError('PDF privo di pagine')
        for page_index,page in enumerate(doc):
            if page_index>=max_pages:break
            words=page.get_text('words')
            draws=page.get_drawings()
            page_record={'page':page_index+1,'native_words':len(words),
                         'vector_drawing_paths':len(draws),
                         'raster_images':len(page.get_images()),
                         'rotation_degrees':page.rotation}
            pages.append(page_record)
            if words or len(draws)<7:
                page_record['mode']='NATIVE_TEXT_OR_INSUFFICIENT_VECTOR_DATA'
                continue
            img=_render(page)
            annotations=[]
            for kind in COLORS:
                mask=_mask_color(img,kind)
                components=_components(mask)
                grouped=_group_repeat_shapes(components)
                for grp in grouped:
                    record={'page':page_index+1,'color':kind,'occurrences':len(grp['items']),
                            'nominal_width_px':grp['width'],'nominal_height_px':grp['height'],
                            'bounding_boxes_px':[r['box'] for r in grp['items']],
                            'status':'RIPETIZIONE_GEOMETRICA_NON_CLASSIFICATA',
                            'verified_device_count':0}
                    all_groups.append(record)
                    annotations.append(record)
                page_record[kind+'_components']=len(components)
                page_record[kind+'_repeated_groups']=len(grouped)
            page_record['mode']='VECTOR_CAD_DIAGNOSTIC_ONLY'
            canvas=img.copy()
            pen=ImageDraw.Draw(canvas)
            for idx,grp in enumerate(sorted(annotations,key=lambda g:(-g['occurrences'],g['color']))):
                for bounds in grp['bounding_boxes_px']:
                    pen.rectangle(bounds,outline=COLORS[grp['color']],width=2)
                bounds=grp['bounding_boxes_px'][0]
                pen.text((bounds[0],max(0,bounds[1]-12)),f'G{idx+1} x{grp["occurrences"]}',
                         fill=COLORS[grp['color']])
            previews.append((page_index+1,canvas))
    result={'schema':'sld-alpha17-vector-triage/v1','source_pdf':str(pdf),
            'native_text_recognition_available':any(p['native_words'] for p in pages),
            'pages_sampled':len(pages),'pages':pages,'geometric_repeat_groups':all_groups,
            'verified_CU':None,'verified_TR':None,'verified_inverters':None,'verified_string_boxes':None,
            'electrical_connections_verified':0,'matrix_flow_import_ready':False,
            'result_status':'DIAGNOSTICA_GEOMETRICA_NON_GERARCHIA_SAP',
            'caveat':'Le ripetizioni sono componenti grafici, NON conteggi di asset. Nessun TXT Ground Truth utilizzato.'}
    if compare_pdf:
        other=Path(compare_pdf)
        if not other.is_file():raise FileNotFoundError(other)
        result['cross_document_comparison']={'other_pdf':str(other),**_compare_rasters(pdf,other)}
    return result, previews


def write_vector_outputs(result, previews, output):
    dest=Path(output); dest.mkdir(parents=True,exist_ok=True)
    (dest/'alpha17_diagnostica_geometrica.json').write_text(
        json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    with (dest/'alpha17_motivi_ripetuti.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,delimiter=';')
        writer.writerow(['pagina','colore','ripetizioni','larghezza_px','altezza_px','stato','coordinate_riquadri_px'])
        for g in result['geometric_repeat_groups']:
            writer.writerow([g['page'],g['color'],g['occurrences'],g['nominal_width_px'],
                             g['nominal_height_px'],g['status'],json.dumps(g['bounding_boxes_px'])])
    for page,img in previews:
        img.save(dest/f'alpha17_anteprima_geometria_p{page}.png')
    return dest
