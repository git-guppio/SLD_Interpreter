"""One-pass, *optional offline* OCR of vector-outlined PV combiner tags.

The page has no native PDF words. A single targeted crop is submitted once to
an installed local Tesseract executable; no remote APIs, no iterative OCR over
candidates. OCR results support a QPS count only when ALL sequence members
1..N agree with independent graphical cabinet detections.

QPS cabinet counts are NEVER silently translated to SAP String Box counts.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

try:
    import pymupdf as fitz
except ImportError:
    import fitz

_QPS = re.compile(r"(?i)(?<!\w)(?P<prefix>QPS|OPS|0PS|APS|PS)\s*[-–]\s*"
                  r"(?P<group>\d{1,3})\s*[-–]\s*(?P<index>\d{1,3})\s*/\s*"
                  r"(?P<total>\d{1,3})(?!\w)")


def parse_qps_ocr_tsv(tsv_text,*,image_bbox,display_scale):
    """Parse TSV items, map their center into the 1000px source raster space.

    Display scale is generated pixel / Alpha18 raster pixel. Non-QPS text is
    ignored; ambiguous OCR prefix is disclosed, not laundered as native text.
    """
    found=[]
    for line in csv.DictReader(io.StringIO(tsv_text),delimiter='\t'):
        text=(line.get('text') or '').strip()
        match=_QPS.search(text)
        if match is None:continue
        try:
            group,index,total=(int(match[k]) for k in ('group','index','total'))
            confidence=float(line.get('conf') or -1)
            x=(float(line['left'])+float(line['width'])/2)/display_scale+image_bbox[0]
            y=(float(line['top'])+float(line['height'])/2)/display_scale+image_bbox[1]
        except (KeyError,ValueError,ZeroDivisionError):continue
        if not (1<=index<=total<=128 and group>=1):continue
        found.append({'text_as_ocr':text,'normalized_designator':f'QPS-{group}-{index}/{total}',
                      'group_on_drawing':group,'sequence_index':index,'sequence_total':total,
                      'recognition_confidence':round(confidence,1),
                      'ocr_prefix_exact':match['prefix'].upper()=='QPS',
                      'center_px':[round(x,2),round(y,2)]})
    return found


def reconcile_qps_sequences(ocr_tokens, fields):
    """Only complete numbered sequences + matching graphic count pass.

    Group identity is corroborated by the coordinates of the actual drawn
    cabinets; an OCR label elsewhere cannot create a field or String Box.
    """
    rows=[]
    for field in fields:
        boxes=field.get('candidate_cabinet_evidence') or []
        if not boxes:
            rows.append({'field_candidate':field['field_candidate'],
                         'ocr_qps_identifiers':0,'graphic_dc_cabinets':0,
                         'qps_documented_count':None,'sequence_complete':False,
                         'source':'NOT_OBSERVED','ocr_tokens':[]})
            continue
        xleft=min(b['bbox_px'][0] for b in boxes)-8
        xright=max(b['bbox_px'][2] for b in boxes)+8
        found=[t for t in ocr_tokens if xleft<=t['center_px'][0]<=xright]
        groups={x['group_on_drawing'] for x in found}
        totals={x['sequence_total'] for x in found}
        ordinal=[x['sequence_index'] for x in found]
        n=len(boxes)
        complete=(len(groups)==1 and len(totals)==1 and
                  totals=={n} and len(ordinal)==n and set(ordinal)==set(range(1,n+1)))
        rows.append({'field_candidate':field['field_candidate'],
                     'ocr_qps_identifiers':len(found),'graphic_dc_cabinets':n,
                     'qps_documented_count':n if complete else None,
                     'sequence_complete':complete,
                     'source':'ONE_LOCAL_OCR_PASS_PLUS_INDEPENDENT_PDF_GEOMETRY' if complete else
                              'OCR_INCOMPLETE_OR_CONFLICT',
                     'ocr_tokens':found,
                     'mapping_to_SAP_string_box':'UNRESOLVED',
                     'string_box_count_for_matrix_flow':None})
    # Two distinct cabinet fields on the same sheet must not both claim the
    # same complete indexed QPS group; duplicate identities require review.
    groups_seen={}
    for row in rows:
        if not row['sequence_complete']:
            continue
        group=row['ocr_tokens'][0]['group_on_drawing']
        groups_seen.setdefault(group,[]).append(row)
    for occurrences in groups_seen.values():
        if len(occurrences)>1:
            for row in occurrences:
                row['sequence_complete']=False
                row['qps_documented_count']=None
                row['source']='DUPLICATE_QPS_GROUP_ACROSS_GRAPHIC_FIELDS'
    return rows


def find_local_tesseract(executable=None):
    if executable:
        path=Path(executable)
        if path.is_file():return str(path)
        return shutil.which(executable)
    p=shutil.which('tesseract')
    if p:return p
    for path in (r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                 r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'):
        if Path(path).is_file():return path
    return None


def recognize_qps_once(pdf_path, fields,*,executable=None, page_number=1, timeout_sec=45):
    """At most ONE local OCR subprocess for the selected CAD page / ROI.

    The original PDF is never changed. This tool does not download software.
    Errors/absence are recorded as ABSTAIN, not 'zero QPS found'.
    """
    exe=find_local_tesseract(executable)
    default={'status':'OCR_NOT_AVAILABLE','tokens':[], 'field_sequences':[],
             'ocr_calls':0,'source_pdf':str(pdf_path),'remote_services_used':False}
    if not exe:return default
    boxes=[c['bbox_px'] for f in fields for c in f.get('candidate_cabinet_evidence',[])]
    if not boxes:return {**default,'status':'NO_GRAPHIC_CABINET_REGION'}
    with fitz.open(str(pdf_path)) as pdf:
        if len(pdf)<page_number or page_number<1:return {**default,'status':'PAGE_MISSING'}
        page=pdf[page_number-1]
        if page.get_text('words'):
            return {**default,'status':'NATIVE_TEXT_PRESENT_USE_TEXT_ENGINE'}
        k=max(page.rect.width,page.rect.height)/1000
        x0=max(0,min(c[0] for c in boxes)-12)
        y0=max(0,min(c[1] for c in boxes)-15)
        x1=min(page.rect.width/k,max(c[2] for c in boxes)+12)
        y1=min(page.rect.height/k,max(c[3] for c in boxes)+15)
        region=[x0,y0,x1,y1]
        # One moderately high resolution crop, bounded to avoid huge OCR jobs.
        render_zoom=2.6
        expected_w=(x1-x0)*k*render_zoom
        if expected_w>7000:render_zoom*=7000/expected_w
        pix=page.get_pixmap(matrix=fitz.Matrix(render_zoom,render_zoom),
                           clip=fitz.Rect(x0*k,y0*k,x1*k,y1*k),alpha=False)
        if pix.width<40 or pix.height<20:return {**default,'status':'EMPTY_CROP'}
        display_scale=pix.width/(x1-x0)
        with tempfile.TemporaryDirectory(prefix='sld_local_ocr_') as t:
            img=Path(t)/'cad_region.png'
            pix.save(str(img))
            try:
                run=subprocess.run([exe,str(img),'stdout','-l','eng','--psm','11','tsv'],
                                   capture_output=True,text=True,timeout=timeout_sec,
                                   check=False,errors='replace')
            except (OSError,subprocess.TimeoutExpired) as exc:
                return {**default,'status':'OCR_FAILED_OR_TIMEOUT','error':str(exc),'ocr_calls':1}
        if run.returncode!=0:
            return {**default,'status':'OCR_FAILED','stderr':run.stderr[:500],'ocr_calls':1}
    words=parse_qps_ocr_tsv(run.stdout,image_bbox=region,display_scale=display_scale)
    sequences=reconcile_qps_sequences(words,fields)
    return {'status':'OCR_DONE','tokens':words,'field_sequences':sequences,
            'ocr_calls':1,'crop_bbox_alpha18_px':region,'source_pdf':str(pdf_path),
            'remote_services_used':False,
            'number_of_complete_qps_fields':sum(x['sequence_complete'] for x in sequences),
            'qps_cabinets_correlated':sum(x['qps_documented_count'] or 0 for x in sequences),
            'string_box_count_for_matrix_flow':None}
