"""Beta3 Alpha 7: conservative, plant-agnostic SLD page routing and review targets.

New evidence types are not inferred electrical connections. This preflight does
not use benchmark expectations, layout group sizes, plant-specific templates or
other-plant knowledge. Existing dev14c and alpha4 reports remain independent.

Modes reflect available *evidence*, not an assumed drafting convention:
- local, same-page electrical identity tags -> bounded vector review regions;
- cross-sheet references -> documentary candidates only (never auto-wired);
- no native text -> OCR required, optional preview using external Tesseract.

All outputs retain page/bbox/provenance and explicit nonverification flags.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata

import pymupdf
from .symbol_terminals import inspect_local_tag
from .geometry_first import inspect_page_geometry

SCHEMA = 'sld-beta3-multistyle-preflight/v1'
# Local ids must be sufficiently discriminating to avoid promoting plain
# transformer mentions, footnotes or index entries into physical assets.
_TAG_PATTERNS = (
    ('TRANSFORMER_TAG', re.compile(r'\b[A-Z0-9]{2,12}[-_]TPO[-_]\d{1,3}[-_]\d{1,3}\b',re.I)),
    ('TRANSFORMER_TAG', re.compile(r'\bXFR[-_ ]?\d{1,3}(?:[.]\d+)?\b',re.I)),
    ('INVERTER_TAG', re.compile(r'\b(?:[A-Z0-9]{2,12}[-_]INV[-_]\d{1,3}[-_]\d{1,3}|INV[.]\d{1,3}[.]\d{1,3})\b',re.I)),
    ('SWITCHGEAR_TAG', re.compile(r'\b[A-Z0-9]{2,12}[-_]CTR[-_]\d{1,3}\b',re.I)),
    ('COMBINER_TAG', re.compile(r'\b[A-Z0-9]{2,12}[-_]CST[-_]\d{1,3}[-_]I\d{1,3}[-_][A-Z0-9-]+\b',re.I)),
)
_MATCHLINE = re.compile(r'\bMATCH\s*LINE\b|\bMATCHLINE\b', re.I)
_SHEET = re.compile(r'\b(?:SEE|REFER\s+TO|VER|VOIR)\s+(?:SHEETS?|PLANOS?|DRAWINGS?)\b',re.I)
_DRAWING_ID = re.compile(r'\b[A-Z]{1,3}-\d{2,4}[A-Z]?\b', re.I)
_CU_REF = re.compile(r'\b(?:A|DE|DA|TO|FROM|PARA|DESDE)\s+SUBCAMPO\s*[-:#]?\s*\d+\b', re.I)
_OCR_TERMS = re.compile(r'\b(?:TRANSFORMADOR|TRANSFORMER|INVERTER|INVERSOR|CELDA|SWITCHGEAR|XFR|SUBCAMPO)\b',re.I)


def _norm(s):
    s = unicodedata.normalize('NFKD',str(s))
    return ''.join(c for c in s if not unicodedata.combining(c)).upper()


def _canonical_tag(tag_type,tag):
    """Normalize safe display variants; never decide physical asset identity."""
    value=_norm(tag).replace('_','-').strip()
    if tag_type=='TRANSFORMER_TAG' and re.fullmatch(r'XFR[ .-]*\d+(?:[.]\d+)?',value):
        return 'XFR-'+re.sub(r'^XFR[ .-]*','',value)
    return value


def _bbox(b):
    return [round(float(x),3) for x in b]


def _lines(page):
    """Yield native PDF text lines with their own geometry, no guessed reading order."""
    for block in page.get_text('dict').get('blocks',()):
        for line in block.get('lines',()):
            spans=line.get('spans') or ()
            text=' '.join(str(sp.get('text') or '') for sp in spans).strip()
            if text and len(text)<350:
                yield {'text':text,'bbox':_bbox(line['bbox'])}


def classify_page_lines(lines, page_number):
    """Documentary refs and unique equipment tags without plant assumptions.

    MATCHLINE is a *graphic boundary*, not proof of electrical continuity.
    SHEET refs in notes are *document pointers*, not links. Ambiguous bare
    target IDs are not matched to other pages.
    """
    refs=[]; devices=[];seen=set()
    for item in lines:
        text=item['text'].strip(); normalized=_norm(text)
        refkind=None
        if _MATCHLINE.search(normalized):
            refkind='GRAPHIC_MATCHLINE_UNQUALIFIED'
        elif _CU_REF.search(normalized):
            refkind='CU_CONTINUATION_UNPAIRED'
        elif _SHEET.search(normalized):
            refkind='DRAWING_POINTER_NOT_ELECTRICAL'
        if refkind:
            refs.append({'page':page_number,'text':text,'bbox':item['bbox'],
                         'reference_kind':refkind,
                         'sheet_id_candidates':sorted(set(_DRAWING_ID.findall(normalized))),
                         'source':'NATIVE_PDF_TEXT',
                         'reciprocal_reference_verified':False,
                         'electrical_connection_verified':False})
        # Avoid index/notes references: only accept isolated equipment tags,
        # not dozens of references in the same long text line.
        if len(text)>100 or refkind:
            continue
        for kind,pat in _TAG_PATTERNS:
            for match in pat.finditer(normalized):
                tag=match.group(0).replace('_','-')
                key=(kind,tag,tuple(item['bbox']))
                if key not in seen:
                    seen.add(key)
                    devices.append({'page':page_number,'tag':tag,'tag_type':kind,
                                    'text':text,'bbox':item['bbox'],
                                    'source':'NATIVE_PDF_TEXT',
                                    'physical_terminal_verified':False,
                                    'graph_verified':False})
    return refs, devices


def _roi_from_box(box, rect, padding=65):
    x0,y0,x1,y1=box
    rect=pymupdf.Rect(rect)
    # PDF pages may be rotated: text and vector geometry are in their shared
    # unrotated MuPDF coordinate space, hence use the CropBox bounds.
    roi=pymupdf.Rect(max(rect.x0,x0-padding),max(rect.y0,y0-padding),
                     min(rect.x1,x1+padding),min(rect.y1,y1+padding))
    return roi if roi.width>=15 and roi.height>=15 else None


def _line_overlaps_roi(p,q,roi):
    """Test segment bounding box only; candidate not conductor connectivity."""
    return max(min(p.x,q.x),roi.x0)<=min(max(p.x,q.x),roi.x1) and max(min(p.y,q.y),roi.y0)<=min(max(p.y,q.y),roi.y1)


def _probe_regions(page, candidates, *, max_regions=3, max_drawings=8500,
                   max_line_items_per_region=50000):
    """ROI-first review of dense PDF vector pages.

    The drawing count limit is deliberately PER REGION. Full-page dense CAD
    vector pages are not discarded. Geometry remains documentary evidence.
    """
    if not candidates or max_regions<=0:
        return [],'NO_DEVICE_TAGS_OR_BUDGET'
    if max_drawings<=0:
        return [],'DRAWING_COMPLEXITY_SAFETY_CAP'
    priorities={'TRANSFORMER_TAG':0,'SWITCHGEAR_TAG':1,'INVERTER_TAG':2,'COMBINER_TAG':3}
    devices=sorted(candidates,key=lambda a:(priorities.get(a['tag_type'],9),a['bbox'][1],a['tag']))
    selection=[];seen=set()
    for d in devices:
        key=(d['tag_type'],d['tag'])
        if key in seen:continue
        seen.add(key)
        roi=_roi_from_box(d['bbox'],page.cropbox)
        if roi is not None:selection.append((d,roi))
        if len(selection)>=max_regions:break
    if not selection:return [],'NO_USABLE_DEVICE_REGION'
    # cdrawings gives lightweight tuples, with drawing bounding boxes. Unlike
    # get_drawings(), we never expand whole-page path objects into Point lists.
    # Do not cap the whole page: PV4 has pages with >200,000 micro paths.
    drawings=page.get_cdrawings()
    native_lines=list(_lines(page))
    total=len(drawings)
    region_drawings=[[] for _ in selection]
    for draw_idx,d in enumerate(drawings):
        if d.get('type') not in ('s','fs','sf'):continue
        rect=d.get('rect')
        if rect is None:continue
        r=pymupdf.Rect(rect)
        for ri,(_,roi) in enumerate(selection):
            if (r.x0<=roi.x1 and r.x1>=roi.x0 and
                r.y0<=roi.y1 and r.y1>=roi.y0):
                # Keep bounded lists per ROI, without stopping other ROIs.
                if len(region_drawings[ri])<=max_drawings:
                    region_drawings[ri].append((draw_idx,d))
    result=[];any_cap=False
    for (dev,roi), nearby in zip(selection,region_drawings):
        if len(nearby)>max_drawings:
            any_cap=True
            result.append({'page':dev['page'],'tag':dev['tag'],'tag_type':dev['tag_type'],
                'source_bbox':dev['bbox'],'roi':_bbox(roi),
                'page_total_vector_drawings':total,
                'vector_drawings_near_roi_lower_bound':len(nearby),
                'solid_line_segments_overlapping_roi':None,
                'short_segment_candidates':None,'segment_evidence_sample':[],
                'status':'ROI_COMPLEXITY_SAFETY_CAP', 'terminal_bound':False,'path_verified':False,
                'alpha7_symbol_terminal':{'decision':'NOT_EVALUATED_SAFETY_CAP',
                    'symbol_hypotheses':[], 'possible_contact_points':[],
                    'device_terminals_verified':0,'through_device_paths_verified':0},
                'note':'Per-ROI safety cap; page not globally discarded'})
            continue
        count=0;short_count=0;skipped_dashes=0;sample=[];limit_hit=False
        cx,cy=(dev['bbox'][0]+dev['bbox'][2])/2,(dev['bbox'][1]+dev['bbox'][3])/2
        line_items_seen=0
        for di,d in nearby:
            dash=str(d.get('dashes','[] 0')).strip()
            if dash not in ('[] 0','[] 0.0','None',''):
                skipped_dashes+=1
                continue
            for j,item in enumerate(d.get('items',())):
                if item[0]!='l':continue
                line_items_seen+=1
                if line_items_seen>max_line_items_per_region:
                    limit_hit=True;break
                # cdrawings items are bare (x,y) tuples, not fitz.Point.
                p,q=item[1],item[2]
                px,py=float(p[0]),float(p[1]);qx,qy=float(q[0]),float(q[1])
                if not _line_overlaps_roi(pymupdf.Point(px,py),pymupdf.Point(qx,qy),roi):continue
                ln=math.hypot(px-qx,py-qy)
                if ln<16:
                    short_count+=1
                    continue  # never merge CAD micro-segments into conductors
                sid=f"P{dev['page']}_D{di}_I{j}"
                count+=1
                distance=min(math.hypot(px-cx,py-cy),math.hypot(qx-cx,qy-cy))
                item_evidence={'source_stroke_id':sid,'from':_bbox((px,py)),
                               'to':_bbox((qx,qy)),'is_electrical_terminal_verified':False}
                sample.append((distance,sid,item_evidence))
                # Keep only the nearest 12 source segments; bounded memory.
                if len(sample)>12:
                    sample.sort(key=lambda v:(v[0],v[1]))
                    sample.pop()
            if limit_hit:break
        sample.sort(key=lambda v:(v[0],v[1]))
        if limit_hit:any_cap=True
        symbol_review=({'decision':'NOT_EVALUATED_SAFETY_CAP',
                     'symbol_hypotheses':[], 'possible_contact_points':[],
                     'device_terminals_verified':0,'through_device_paths_verified':0}
                    if limit_hit else inspect_local_tag(dev,nearby,roi,native_lines))
        status=('ROI_LINE_ITEM_SAFETY_CAP' if limit_hit else
                'VECTOR_NEIGHBORHOOD_CANDIDATE' if count else
                'MICRO_STROKES_PRESENT_UNRESOLVED' if short_count else
                'NO_LOCAL_VECTOR_STROKES')
        result.append({'page':dev['page'],'tag':dev['tag'],'tag_type':dev['tag_type'],
               'source_bbox':dev['bbox'],'roi':_bbox(roi),
               'page_total_vector_drawings':total,'vector_drawings_near_roi':len(nearby),
               'solid_line_segments_overlapping_roi':count,
               'short_segment_candidates':short_count,
               'dashed_drawings_excluded':skipped_dashes,
               'segment_evidence_sample':[item[2] for item in sample],
               'segment_evidence_sample_truncated':count>len(sample),
               'alpha7_symbol_terminal':symbol_review,
               'status':status,'terminal_bound':False,'path_verified':False,
               'note':'Geometric ROI only; no device terminal or connectivity assertion'})
    # Avoid counting the same two-ring drawing against two nearby tags. This is
    # deliberately decided across all inspected ROIs, not independently per tag.
    pair_owners={}
    for entry in result:
        diag=entry.get('alpha7_symbol_terminal') or {}
        for sym in diag.get('symbol_hypotheses',[]):
            pair_key=tuple(sorted(sym['circle_drawing_ids']))
            pair_owners.setdefault(pair_key,set()).add((entry['tag_type'],entry['tag']))
    collisions={k for k,v in pair_owners.items() if len(v)>1}
    if collisions:
        for entry in result:
            diag=entry.get('alpha7_symbol_terminal') or {}
            if any(tuple(sorted(sym['circle_drawing_ids'])) in collisions
                   for sym in diag.get('symbol_hypotheses',[])):
                diag['decision']='SAME_SYMBOL_CANDIDATE_FOR_MULTIPLE_TAGS'
                diag['possible_contact_points']=[]  # no chosen identity
                diag['symbol_tag_collision']=True
    return result,'PARTIAL_ROI_SAFETY_CAP' if any_cap else 'COMPLETE_DIAGNOSTIC'


def summarize_tag_identities(pages):
    """Canonical *tag strings*, NOT canonical equipment assets.

    Repeated occurrences retain all their source pages and boxes. This avoids
    summing repeated tags while making no claim that reused tags are the same
    physical device without site-specific contextual verification.
    """
    groups={}
    for row in pages:
        for d in row['named_devices']:
            key=(d['tag_type'],_canonical_tag(d['tag_type'],d['tag']))
            g=groups.setdefault(key,{'tag_type':key[0],'tag':key[1],
                'observed_tag_spellings':[],
                'identity_status':'UNVERIFIED_TAG_STRING','occurrences':[]})
            if d['tag'] not in g['observed_tag_spellings']:
                g['observed_tag_spellings'].append(d['tag'])
            g['occurrences'].append({'page':d['page'],'bbox':d['bbox'],
                                      'source':d['source']})
    result=[]
    for key,g in sorted(groups.items()):
        g['mention_count']=len(g['occurrences'])
        g['page_count']=len({o['page'] for o in g['occurrences']})
        g['identity_status']=('REPEATED_TAG_REQUIRES_IDENTITY_REVIEW'
                    if g['mention_count']>1 else 'SINGLE_TAG_UNVERIFIED_ASSET')
        result.append(g)
    return result

def _ocr_preview(page, *, executable=None, dpi=90, timeout=25):
    """Optional OCR on a single page, independent evidence layer, never an asset.

    Tesseract is external and might not be installed on the user's Windows PC.
    Defaults to OFF in audit; only run on explicit --ocr-preview request.
    """
    exe=executable or shutil.which('tesseract')
    if not exe:
        return {'status':'DEPENDENCY_UNAVAILABLE','engine':'TESSERACT', 'items':[]}
    pix=page.get_pixmap(matrix=pymupdf.Matrix(dpi/72,dpi/72),alpha=False)
    with tempfile.TemporaryDirectory(prefix='sld_alpha5_ocr_') as temp:
        png=Path(temp)/'ocr.png'
        pix.save(str(png))
        try:
            p=subprocess.run([exe,str(png),'stdout','tsv','--psm','11'],
                capture_output=True,text=True,timeout=timeout,check=False)
        except (subprocess.TimeoutExpired,OSError) as exc:
            return {'status':'OCR_FAILED','reason':type(exc).__name__,'items':[]}
    if p.returncode:
        return {'status':'OCR_FAILED','reason':p.stderr[-250:],'items':[]}
    hits=[]
    lines=p.stdout.splitlines()
    for ln in lines[1:]:
        fields=ln.split('\t',11)
        if len(fields)!=12:continue
        token=fields[-1].strip()
        if not token or not (_OCR_TERMS.search(token) or re.search(r'(?:TPO|CTR|XFR|INV)[-_]?\d+',token,re.I)):
            continue
        try:
            confidence=float(fields[10])
            x,y,w,h=[int(fields[j]) for j in (6,7,8,9)]
        except (ValueError,IndexError):continue
        if confidence<40:continue
        scale=72/dpi
        hits.append({'text':token,'bbox':_bbox([x*scale,y*scale,(x+w)*scale,(y+h)*scale]),
                     'confidence':round(confidence,1),'source':'OCR_TESSERACT_PREVIEW',
                     'device_identity_verified':False})
    return {'status':'OCR_PREVIEW_ONLY','engine':'TESSERACT','items':hits[:80],
            'note':'OCR text alone cannot establish tags, symbol identities or topology'}


def audit_multistyle(pdf_path, *, max_pages=None, max_probe_pages=3,
                     regions_per_page=3, ocr_preview=False, max_ocr_pages=1,
                     max_drawings=8500, plant_id=None,
                     geometry_first_pages=0, geometry_first_max_groups=30):
    """Diagnostic generalization across differing SLD conventions."""
    p=Path(pdf_path)
    if not p.is_file():raise FileNotFoundError(p)
    if max_pages is not None and max_pages<1:raise ValueError('max_pages must be positive')
    if min(max_probe_pages,regions_per_page,max_ocr_pages,geometry_first_pages,geometry_first_max_groups)<0:
        raise ValueError('Budgets must be nonnegative')
    pages=[]; summaries=Counter()
    with pymupdf.open(p) as doc:
        if len(doc)<1:raise ValueError('Empty PDF')
        total_pages=len(doc)
        n=min(max_pages or total_pages,total_pages)
        for index in range(n):
            page=doc[index]
            lines=list(_lines(page))
            refs,devs=classify_page_lines(lines,index+1)
            modes=[]
            if any(r['reference_kind']=='CU_CONTINUATION_UNPAIRED' for r in refs):modes.append('CU_CROSS_SHEET_DOCUMENTARY')
            if any(r['reference_kind']=='GRAPHIC_MATCHLINE_UNQUALIFIED' for r in refs):modes.append('MATCHLINE_DOCUMENTARY_UNQUALIFIED')
            if any(r['reference_kind']=='DRAWING_POINTER_NOT_ELECTRICAL' for r in refs):modes.append('DRAWING_REFERENCE_ONLY')
            if devs:modes.append('LOCAL_TAGGED_EQUIPMENT')
            if not lines:modes.append('NO_NATIVE_TEXT_OCR_ELIGIBLE')
            if not modes:modes.append('NATIVE_TEXT_NO_CLASSIFIED_EVIDENCE')
            rows={'page':index+1,'native_text_lines':len(lines),
                  'page_width_pt':round(page.rect.width,2), 'page_height_pt':round(page.rect.height,2),
                  'modes':modes,'references':refs,'named_devices':devs,
                  'local_vector_reviews':[], 'geometry_status':'NOT_REQUESTED',
                  'geometry_first':{'status':'NOT_REQUESTED','hypotheses':[], 'source_scan_complete':False},
                  'ocr_preview':{'status':'NOT_REQUESTED'},
                  'graph_verified_electrical_connections':0}
            pages.append(rows)
            for mode in modes:summaries['mode:'+mode]+=1
            summaries['references']+=len(refs)
            summaries['named_devices']+=len(devs)
        # Spend vector budget on pages that have real named tags, not ref-only
        # pages. Coverage is reported, never implied full-page verification.
        # Prefer pages containing tag classes with a supported Alpha7 symbol
        # hypothesis (TPO transformers) over pages packed with combiner tags.
        # This is explicitly sample prioritization, never a completeness claim.
        candidates=sorted((row for row in pages if row['named_devices']),
                          key=lambda row:(
                              -sum(d['tag_type']=='TRANSFORMER_TAG' and '-TPO-' in d['tag']
                                   for d in row['named_devices']),
                              -sum(d['tag_type']=='TRANSFORMER_TAG' for d in row['named_devices']),
                              -len(row['named_devices']),row['page']))
        for row in candidates[:max_probe_pages]:
            page=doc[row['page']-1]
            regions, status=_probe_regions(page,row['named_devices'],
                       max_regions=regions_per_page,max_drawings=max_drawings)
            row['local_vector_reviews']=regions
            row['geometry_status']=status
            summaries['pages_geometry_probe_attempted']+=1
            summaries['local_vector_review_regions']+=len(regions)
        # Alpha8 second, independent route: look at actual path geometry, even
        # where the PDF has no native text, tags, or successful OCR. Do not
        # deduce equipment from an unlabelled circle group.
        if geometry_first_pages:
            geometry_order=sorted(pages,key=lambda r:(
                bool(r['named_devices']), bool(r['native_text_lines']),r['page']))
            for row in geometry_order[:geometry_first_pages]:
                diagnostic=inspect_page_geometry(doc[row['page']-1],page_number=row['page'],
                    max_groups=geometry_first_max_groups)
                row['geometry_first']=diagnostic
                summaries['alpha8_geometry_first_pages_attempted']+=1
                summaries['alpha8_geometry_first_hypotheses_unverified']+=len(diagnostic['hypotheses'])
                summaries['alpha8_geometry_first_safety_caps']+=int(not diagnostic['source_scan_complete'])
                summaries['alpha8_geometry_first_unreported_groups']+=diagnostic.get('omitted_hypotheses') or 0
        if ocr_preview:
            for row in (r for r in pages if 'NO_NATIVE_TEXT_OCR_ELIGIBLE' in r['modes']):
                if summaries['pages_ocr_attempted']>=max_ocr_pages:break
                row['ocr_preview']=_ocr_preview(doc[row['page']-1])
                summaries['pages_ocr_attempted']+=1
                summaries['ocr_hint_tokens']+=len(row['ocr_preview'].get('items',[]))
    identities=summarize_tag_identities(pages)
    return {'schema':SCHEMA,'status':'PARTIAL_PAGE_SAMPLE' if n<total_pages else 'COMPLETE_PAGE_TRIAGE',
            'source':{'file_name':p.name,'page_count':total_pages,'pages_classified':n,
                      'plant_id':plant_id,'input_read_only':True},
            'summary':{'pages_scanned':n,'total_pages':total_pages,'pages_with_named_equipment':sum(bool(r['named_devices']) for r in pages),
                       'pages_with_matchline':summaries['mode:MATCHLINE_DOCUMENTARY_UNQUALIFIED'],
                       'pages_with_drawing_reference':summaries['mode:DRAWING_REFERENCE_ONLY'],
                       'pages_with_cu_continuation':summaries['mode:CU_CROSS_SHEET_DOCUMENTARY'],
                       'pages_without_native_text':summaries['mode:NO_NATIVE_TEXT_OCR_ELIGIBLE'],
                       'reference_occurrences_classified':summaries['references'],
                       'device_tag_occurrences':summaries['named_devices'],
                       'distinct_device_tag_strings':len({d['tag'] for row in pages for d in row['named_devices']}),
                       'unverified_distinct_tag_type_pairs':len(identities),
                       'repeated_tag_type_pairs':sum(g['mention_count']>1 for g in identities),
                       'tag_occurrences_exceeding_unique_tag_keys':sum(g['mention_count']-1 for g in identities),
                       'local_geometry_regions_with_candidates':sum(r['status']=='VECTOR_NEIGHBORHOOD_CANDIDATE' for row in pages for r in row['local_vector_reviews']),
                       'roi_safety_cap_regions':sum('SAFETY_CAP' in r['status'] for row in pages for r in row['local_vector_reviews']),
                       'pages_geometry_probe_attempted':summaries['pages_geometry_probe_attempted'],
                       'pages_geometry_probe_skipped_by_sampling_budget':max(0,sum(bool(r['named_devices']) for r in pages)-summaries['pages_geometry_probe_attempted']),
                       'local_vector_review_regions':summaries['local_vector_review_regions'],
                       'alpha7_paired_circle_symbol_candidates':sum(
                         len(rev.get('alpha7_symbol_terminal',{}).get('symbol_hypotheses',[]))
                         for row in pages for rev in row['local_vector_reviews']),
                       'alpha7_possible_edge_contacts_unverified':sum(
                         len(rev.get('alpha7_symbol_terminal',{}).get('possible_contact_points',[]))
                         for row in pages for rev in row['local_vector_reviews']),
                       'alpha7_drawing_note_regions':sum(
                         bool(rev.get('alpha7_symbol_terminal',{}).get('drawing_note_cues'))
                         for row in pages for rev in row['local_vector_reviews']),
                       'alpha7_symbol_tag_collision_regions':sum(
                         rev.get('alpha7_symbol_terminal',{}).get('symbol_tag_collision',False)
                         for row in pages for rev in row['local_vector_reviews']),
                       'alpha7_unique_pair_drawings_unverified':len({
                         (row['page'], tuple(sorted(hyp['circle_drawing_ids'])))
                         for row in pages for rev in row['local_vector_reviews']
                         for hyp in rev.get('alpha7_symbol_terminal',{}).get('symbol_hypotheses',[]) }),
                       'alpha8_geometry_first_pages_attempted':summaries['alpha8_geometry_first_pages_attempted'],
                       'alpha8_geometry_first_pages_skipped_budget':n-summaries['alpha8_geometry_first_pages_attempted'] if geometry_first_pages else n,
                       'alpha8_geometry_first_hypotheses_unverified':summaries['alpha8_geometry_first_hypotheses_unverified'],
                       'alpha8_geometry_first_safety_caps':summaries['alpha8_geometry_first_safety_caps'],
                       'alpha8_geometry_first_unreported_groups':summaries['alpha8_geometry_first_unreported_groups'],
                       'pages_ocr_attempted':summaries['pages_ocr_attempted'],
                       'ocr_hint_tokens':summaries['ocr_hint_tokens'],
                       'cross_sheet_electrical_links_verified':0,
                       'through_device_paths_verified':0,
                       'graph_verified_feeder_memberships':0},
            'tag_identity_groups':identities,
            'alpha8_geometry_first_review_queue':[
                hyp for row in pages for hyp in row['geometry_first'].get('hypotheses',[])],
            'alpha7_symbol_review_queue':[
                {'page':row['page'], 'tag':rev['tag'], 'tag_type':rev['tag_type'],
                 'bbox':rev['source_bbox'], 'decision':rev.get('alpha7_symbol_terminal',{}).get('decision'),
                 'symbol_candidates':len(rev.get('alpha7_symbol_terminal',{}).get('symbol_hypotheses',[])),
                 'possible_contacts_unverified':len(rev.get('alpha7_symbol_terminal',{}).get('possible_contact_points',[])),
                 'note_context':bool(rev.get('alpha7_symbol_terminal',{}).get('drawing_note_cues')),
                 'physical_asset_confirmed':False,'terminal_confirmed':False,
                 'graph_verified':False}
                for row in pages for rev in row['local_vector_reviews']
                if rev.get('alpha7_symbol_terminal',{}).get('symbol_hypotheses') or
                   rev.get('alpha7_symbol_terminal',{}).get('drawing_note_cues') or
                   rev.get('alpha7_symbol_terminal',{}).get('symbol_tag_collision')],
            'count_provenance':{'native_pdf_tag_mentions':summaries['named_devices'],
                'unique_tag_type_keys_UNVERIFIED':len(identities),
                'native_pdf_symbol_qualified_asset_count':None,
                'explicit_table_asset_count':None,
                'rule_inferred_asset_count':None,
                'canonical_physical_asset_count':None,
                'note':'Missing counts are NOT measured; tag strings never constitute verified asset instances. Do not add evidence categories.'},
            'pages':pages,
            'evidence_policy':('Every reference and local device tag is candidate evidence only. '
                'MATCHLINE and SEE SHEET do not create electrical links. A vector near a tag '
                'does not establish its terminal; an OCR hint never creates an asset. '
                'Alpha7 circular-symbol and point-of-contact proposals are UNVERIFIED. '
                'Alpha8 geometric-source-first ring groups are UNLABELED, UNVERIFIED shape hypotheses. '
                'No electrical through-device path nor feeder association is asserted.')}
