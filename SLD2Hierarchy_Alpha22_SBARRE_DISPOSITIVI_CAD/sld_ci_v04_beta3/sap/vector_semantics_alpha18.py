"""Alpha18: conservative *candidate* recognition on vector-only CAD SLDs.

Read-only, source-grounded. No OCR, no TXT/reference inventories, no
plant-specific file names/IDs, no source modification, no SAP asset assertion.

A candidate converter requires THREE independent graphical features:
(1) a cyan bounded CAD panel, (2) a black diagonal converter-like glyph,
(3) a red horizontal outgoing comb with individually detected branches.
Similar lower cyan panels are separately counted as downstream *enclosures*
without claiming that they are string boxes. Spatial ordering is NOT accepted
as verified TR/INV/SB electrical connectivity.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz
import cv2
import numpy as np
from PIL import ImageDraw, ImageFont

from .vector_diagnostics_alpha17 import (_render, _mask_color, _components,
                                          vector_only_document)


def _red_runs(row, x_offset=0):
    ids = np.flatnonzero(row)
    if not len(ids):
        return []
    breaks = np.flatnonzero(np.diff(ids) > 1)
    chunks = np.split(ids, breaks + 1)
    return [(int(x_offset + c[0]), int(x_offset + c[-1])) for c in chunks]


def _diagonal_present(image_array, box):
    x1, y1, x2, y2 = box
    cut = image_array[y1:y1 + max(8, int((y2-y1)*0.53)), x1:x2]
    if cut.size == 0:
        return False
    # Dark diagonal, beyond simple letter/stroke noise. This is a glyph
    # signature, never an electrical symbol confirmation in isolation.
    gray = cv2.cvtColor(cut, cv2.COLOR_RGB2GRAY)
    lines = cv2.HoughLinesP(cv2.Canny(gray, 55, 150), 1,
                            np.pi/180, threshold=5, minLineLength=4,
                            maxLineGap=2)
    if lines is None:
        return False
    diag = 0
    for raw in lines[:, 0, :]:
        x0, y0, x1l, y1l = (int(v) for v in raw)
        dx, dy = abs(x1l-x0), abs(y1l-y0)
        if dx >= 4 and dy >= 4 and .35 <= dx / dy <= 2.8:
            diag += 1
    return diag >= 2


def _comb_taps(red, box):
    """Count observed outgoing red strokes below the broad horizontal bus.

    Return the count and exact positions. Never turn the count into string
    boxes: one departure can serve multiple downstream boxes.
    """
    x1, y1, x2, y2 = box
    width, height = x2-x1, y2-y1
    if height < 15 or width < 20:
        return [], None
    ys = range(y1+int(.59*height), min(red.shape[0], y1+int(.87*height)))
    if not ys:
        return [], None
    yc = max(ys, key=lambda y: int(red[y, x1:x2].sum()))
    if int(red[yc, x1:x2].sum()) < .60 * width:
        return [], None
    # Prefer rows with isolated taps following the bus. Multiple probes
    # tolerate line weight and raster antialiasing without fixed x positions.
    probes = []
    for delta in range(3, 9):
        y = yc+delta
        if y >= red.shape[0]:break
        runs = _red_runs(red[y, x1:x2], x1)
        taps = [int((a+b)/2) for a,b in runs if b-a <= 3]
        if 2 <= len(taps) <= 32:
            distances = np.diff(taps)
            if len(distances) and min(distances) >= max(2, width/33):
                probes.append((len(taps), taps))
    if not probes:
        return [], int(yc)
    # Choose the modal count, then the probe closest to the bus.
    best_count = max(set(c for c,_ in probes), key=lambda c:(sum(v==c for v,_ in probes),c))
    taps = next(t for count,t in probes if count == best_count)
    if len(taps) >= 3:
        delta = np.diff(taps).astype(float)
        if float(np.std(delta) / np.mean(delta)) > .45:
            return [], int(yc)
    return taps, int(yc)


def _cyan_panel_cells(mask, box):
    """Estimate *outlined compartments*, not string boxes, in one panel."""
    x1,y1,x2,y2 = box
    patch = mask[y1:y2,x1:x2]
    if patch.size == 0:return None
    h,w = patch.shape
    columns = patch.sum(axis=0)
    cut = max(5, round(.57*h))
    peaks = np.flatnonzero(columns>=cut)
    if len(peaks)<3:return None
    chunks = np.split(peaks,np.flatnonzero(np.diff(peaks)>max(4,int(w*.048)))+1)
    centers = [round(float(np.mean(c)),1) for c in chunks if len(c)>0]
    cells = len(centers)-1
    if not 2 <= cells <= 32:return None
    steps = np.diff(centers)
    if (float(np.min(steps)) < 6 or
        float(np.std(steps) / np.mean(steps)) > .25):return None
    return cells


def analyze_vector_page(image):
    """Pure raster-derived candidate extractor, testable on synthetic SLDs."""
    rgb=np.asarray(image.convert('RGB'))
    red=np.asarray(_mask_color(image,'rosso'))>0
    cyan=np.asarray(_mask_color(image,'ciano'))>0
    components=_components(ImageMask(cyan),closing=5,min_area=45,min_wh=11)
    converters=[]
    for component in components:
        box=component['box']
        x1,y1,x2,y2=box
        w,h=x2-x1,y2-y1
        if not (.65 <= w/h <= 1.45 and 22<=w<=rgb.shape[1]*.16 and
                24<=h<=rgb.shape[0]*.19):
            continue
        taps,ybus=_comb_taps(red,box)
        if not (2 <= len(taps) <= 32):
            continue
        diagonal=_diagonal_present(rgb,box)
        converters.append({'bbox_px':box,'outgoing_branches_observed':len(taps),
                           'tap_x_px':taps,'bus_y_px':ybus,
                           '_diagonal':diagonal,
                           'status':'INVERTER_GRAFICO_CANDIDATO_DA_VERIFICARE',
                           'classification_evidence':['CYAN_PANEL',
                                                      'RED_BUS_WITH_SEPARATE_OUTGOING_TAPS'] +
                               (['DARK_DIAGONAL_GLYPH'] if diagonal else [])})
    # Recover a glyph with raster strokes imperfectly traced, but ONLY when
    # two other converters on the same drawing independently exhibit a
    # diagonal glyph and its panel is visually similar. One red comb is not
    # enough to learn a converter class from scratch.
    strong=[c for c in converters if c['_diagonal']]
    def glyph_crop(c):
        x1,y1,x2,y2=c['bbox_px']
        cut=rgb[y1:y1+max(8,int((y2-y1)*.53)),x1:x2]
        gray=cv2.cvtColor(cut,cv2.COLOR_RGB2GRAY)
        return cv2.resize(gray,(70,43)).astype(np.float32)
    for c in converters:
        if c['_diagonal']:
            continue
        if len(strong)<2:
            continue
        x1,y1,x2,y2=c['bbox_px']
        same_size=[s for s in strong if
                   abs((s['bbox_px'][2]-s['bbox_px'][0])-(x2-x1))<=max(3,(x2-x1)*.12) and
                   abs((s['bbox_px'][3]-s['bbox_px'][1])-(y2-y1))<=max(3,(y2-y1)*.12) and
                   abs(s['bbox_px'][1]-y1)<max(7,(y2-y1)*.20)]
        if len(same_size)<2:
            continue
        template=glyph_crop(c).ravel()
        similarity=max(float(np.corrcoef(template,glyph_crop(s).ravel())[0,1])
                       for s in same_size)
        if similarity>=.82:
            c['classification_evidence'].append('REPEATED_GLYPH_MATCH_TO_TWO_INDEPENDENT_CANDIDATES')
            c['template_similarity']=round(similarity,4)
            c['_diagonal']=True
    converters=[c for c in converters if c.pop('_diagonal')]
    converters.sort(key=lambda r:(r['bbox_px'][1],r['bbox_px'][0]))
    # Group only repeated cabinets of similar topological size on one row.
    # Solitary candidates remain shown but unconfirmed.
    for i,entry in enumerate(converters,1):
        entry['candidate_id']=f'INV_GRAFICO_{i:03d}'
    # Keep the field enclosure clustering separate from hierarchy ownership.
    # A downstream panel can be a combiner, switchgear or drawing annotation.
    panels=[]
    for c in components:
        box=c['box'];x1,y1,x2,y2=box
        w,h=x2-x1,y2-y1
        if h<16 or w/h<3 or w>rgb.shape[1]*.48:
            continue
        cells=_cyan_panel_cells(cyan,box)
        if cells is None:
            continue
        if converters and y1<=min(e['bus_y_px'] for e in converters):
            continue
        panels.append({'bbox_px':box,'contained_cyan_compartments':cells,
                       'status':'COMPARTIMENTI_GRAFICI_A_VALLE_NON_CLASSIFICATI'})
    panels.sort(key=lambda e:(e['bbox_px'][1],e['bbox_px'][0]))
    return converters,panels


def group_downstream_panels(panels):
    """Group repeated panels into spatial fields, without claiming INV parent."""
    if not panels:
        return []
    widths=[p['bbox_px'][2]-p['bbox_px'][0] for p in panels]
    median_width=float(np.median(widths))
    groups=[]
    for panel in sorted(panels,key=lambda p:(p['bbox_px'][0]+p['bbox_px'][2])/2):
        cx=(panel['bbox_px'][0]+panel['bbox_px'][2])/2
        if groups and abs(cx-groups[-1]['center_x'])<=.65*median_width:
            g=groups[-1]
            g['items'].append(panel)
            g['center_x']=float(np.mean([(p['bbox_px'][0]+p['bbox_px'][2])/2 for p in g['items']]))
        else:
            groups.append({'center_x':float(cx),'items':[panel]})
    return [{'field_candidate':i,'graphic_panels':len(g['items']),
             'compartments_observed':sum(p['contained_cyan_compartments'] for p in g['items']),
             'page':g['items'][0]['page'],
             'status':'CAMPO_GRAFICO_CANDIDATO_SENZA_PARENT_INVERTER_VERIFICATO',
             'panel_boxes_px':[p['bbox_px'] for p in g['items']]}
            for i,g in enumerate(groups,1) if len(g['items'])>=2]


class ImageMask:
    """Tiny Pillow-compatible adapter for _components, no palette rescan."""
    def __init__(self, mask):
        from PIL import Image
        self._image=Image.fromarray((mask.astype(np.uint8)*255),'L')
    def filter(self, filter_object):
        return self._image.filter(filter_object)


def inspect_vector_semantics(pdf_path, *, max_pages=3):
    pdf=Path(pdf_path)
    if not pdf.is_file():raise FileNotFoundError(pdf)
    result={'schema':'sld-alpha18-cad-candidates/v1','source_pdf':str(pdf),
            'method':'VECTOR_COLOR_TOPOLOGY_NO_NATIVE_TEXT_NO_OCR',
            'pages':[],'converter_candidates':[], 'downstream_graphic_panels':[],
            'downstream_field_candidates':[],
            'verified_CU':None,'verified_TR':None,'verified_inverters':None,
            'verified_string_boxes':None, 'verified_tr_inverter_parent_links':0,
            'matrix_flow_import_ready':False,
            'warning':'Candidati grafici, NON asset SAP confermati. I rami di uscita non equivalgono a String Box.',
            'ground_truth_used':False}
    previews=[]
    with fitz.open(str(pdf)) as doc:
        for index,page in enumerate(doc):
            if index>=max_pages:break
            words=page.get_text('words');draws=page.get_drawings()
            page_record={'page':index+1,'native_words':len(words),'vector_paths':len(draws)}
            result['pages'].append(page_record)
            if words or len(draws)<7:
                page_record['status']='SKIPPED_NATIVE_TEXT_OR_NONVECTOR'
                continue
            img=_render(page)
            converters,panels=analyze_vector_page(img)
            page_record['status']='GRAPHIC_CANDIDATES_NOT_SAP_ASSETS'
            page_record['inverter_like_candidates']=len(converters)
            page_record['downstream_panels']=len(panels)
            for c in converters:
                c['page']=index+1
                result['converter_candidates'].append(c)
            for p in panels:
                p['page']=index+1
                result['downstream_graphic_panels'].append(p)
            result['downstream_field_candidates'].extend(group_downstream_panels(panels))
            # High-resolution preview, with short non-overlapping labels.
            scale=2
            preview=img.resize((img.width*scale,img.height*scale))
            pen=ImageDraw.Draw(preview)
            try:font=ImageFont.load_default(size=15)
            except TypeError:font=ImageFont.load_default()
            for ordinal,c in enumerate(converters,1):
                b=tuple(z*scale for z in c['bbox_px'])
                pen.rectangle(b,outline='#e46b00',width=4)
                pen.text((b[0],max(0,b[1]-24)),
                         f"INV?{ordinal}:{c['outgoing_branches_observed']}",
                         fill='#b84900',font=font)
                for px in c['tap_x_px']:
                    yy=(c['bus_y_px']+5)*scale;xx=px*scale
                    pen.ellipse((xx-3,yy-3,xx+3,yy+3),outline='#e46b00',width=2)
            for p in panels:
                b=tuple(z*scale for z in p['bbox_px'])
                pen.rectangle(b,outline='#2463c9',width=3)
                pen.text((b[0],min(preview.height-18,b[3]+2)),
                         f"{p['contained_cyan_compartments']} elem. grafici",
                         fill='#2463c9',font=font)
            previews.append((index+1,preview))
    return result,previews


def write_semantics_outputs(result,previews,out_dir):
    dest=Path(out_dir);dest.mkdir(parents=True,exist_ok=True)
    (dest/'alpha18_candidati_vettoriali.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (dest/'alpha18_candidati_inverter.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.writer(f,delimiter=';')
        wr.writerow(['pagina','id_candidato','rami_uscita_osservati','stato','bbox_px'])
        for c in result['converter_candidates']:
            wr.writerow([c['page'],c['candidate_id'],c['outgoing_branches_observed'],
                         c['status'],json.dumps(c['bbox_px'])])
    with (dest/'alpha18_compartimenti_grafici.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.writer(f,delimiter=';')
        wr.writerow(['pagina','compartimenti_per_pannello','stato','bbox_px'])
        for p in result['downstream_graphic_panels']:
            wr.writerow([p['page'],p['contained_cyan_compartments'],p['status'],json.dumps(p['bbox_px'])])
    with (dest/'alpha18_campi_grafici.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.writer(f,delimiter=';')
        wr.writerow(['pagina','campo_candidato','pannelli_grafici','compartimenti_osservati',
                     'parent_inverter','stato'])
        for g in result['downstream_field_candidates']:
            wr.writerow([g['page'],g['field_candidate'],g['graphic_panels'],
                         g['compartments_observed'],'NON VERIFICATO',g['status']])
    for page,img in previews:
        img.save(dest/f'alpha18_anteprima_simboli_p{page}.png')
    return dest
