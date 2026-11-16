"""Beta3 independent, read-only anchor-to-vector diagnostics.

A cross-sheet reference can be accompanied by a vector stroke leading toward a
switchgear cell. Finding that stroke does NOT prove physical device terminals,
continuity through any cell, a feeder root, or electrical feeder membership.

No plant templates, GT inputs or benchmark counts. Candidate matching is
conservative: exact page/document provenance, geometric neighbourhood,
solid vector strokes only, unique selection or explicit ambiguity.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import math
import pymupdf
from .cross_sheet import analyze_cross_sheet
from ..geometry.kernel import extract_pdf

SCHEMA = 'sld-beta3-reference-landing/v1'


def _landing_candidates(strokes, bbox):
    """Find long straight strokes immediately beyond a *vertical* label.

    This is a deliberately limited detector; a rotated/horizontal/curved symbol
    must remain unresolved rather than guessed. Tolerances are in PDF points.
    """
    x0,y0,x1,y1 = map(float,bbox)
    if not (x0 < x1 and y0 < y1) or (y1-y0) < 1.4*(x1-x0):
        return [], 'UNSUPPORTED_REFERENCE_ORIENTATION'
    cx=(x0+x1)/2
    hits=[]
    for s in strokes:
        if s.dashed or s.length() < 20:
            continue
        xmid=(s.p1[0]+s.p2[0])/2
        dx=abs(s.p1[0]-s.p2[0]); dy=abs(s.p1[1]-s.p2[1])
        ymin,ymax=sorted([s.p1[1],s.p2[1]])
        if not (dx<=0.7 and 20<=dy<=175 and abs(xmid-cx)<=3.0):
            continue
        if not (y1-3.0<=ymin<=y1+38 and y1+20<=ymax<=y1+180):
            continue
        hits.append({'source_stroke_id':s.sid,'stroke_from':[round(xmid,3),round(ymin,3)],
                     'stroke_to':[round(xmid,3),round(ymax,3)],
                     'length_pt':round(dy,3),
                     'x_offset_to_reference_pt':round(abs(xmid-cx),3),
                     'reference_end_gap_pt':round(ymin-y1,3)})
    # A named reference is NOT evidence that the nearest candidate is conductive;
    # return all matches and refuse to choose when multiple are plausible.
    hits.sort(key=lambda s:(s['x_offset_to_reference_pt'],abs(s['reference_end_gap_pt']),
                            -s['length_pt'],s['source_stroke_id']))
    return hits, None


def _adjacent_mv_cell_labels(page, stroke, bbox):
    """Text cue only: evidence that a LINEA cell label is nearby, not a terminal."""
    x=stroke['stroke_to'][0]
    y1=float(bbox[3])
    cues=[]
    # Adjacent vertical 'CELDA DE' and 'LINEA' normally appear as distinct text
    # spans; keep raw sources so the operator can inspect false positives.
    lines=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            s=''.join(span.get('text','') for span in line.get('spans',[])).upper().strip()
            box=line.get('bbox')
            if not box or not s:
                continue
            if abs((box[0]+box[2])/2-x)<=28 and y1+25<=((box[1]+box[3])/2)<=y1+155:
                if 'CELDA' in s or 'LINEA' in s:
                    lines.append({'text':s,'bbox':[round(float(a),3) for a in box]})
    if any('CELDA' in r['text'] for r in lines) and any('LINEA' in r['text'] for r in lines):
        cues=lines
    return cues


def analyze_reference_landings(base, sld_pdf_path, *, selected_pages=None):
    """Audit physical vector candidate for each reciprocal *SLD* reference.

    Diagnostic means neither full-page graph nor through-device verification.
    `selected_pages` is a diagnostic sampling scope, never a completeness claim.
    """
    path=Path(sld_pdf_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    docinfo=(base.get('sources') or {}).get('sld') or {}
    if docinfo.get('file_name') != path.name:
        raise ValueError('SLD source filename mismatch: refuse to associate positions')
    cross=analyze_cross_sheet(base)
    bypage=defaultdict(list)
    for link in cross['reciprocal_links']:
        for ref in link['evidence']:
            bypage[ref['page']].append((link,ref))
    results=[]
    n_uninspected=0
    with pymupdf.open(path) as doc:
        if docinfo.get('page_count')!=len(doc):
            raise ValueError('SLD page count mismatch: refuse to associate positions')
        for n in sorted(bypage):
            refs=bypage[n]
            if selected_pages is not None and n not in selected_pages:
                n_uninspected+=len(refs)
                continue
            page=doc[n-1]
            strokes, ignored, dots=extract_pdf(page,page_number=n)
            for link,ref in refs:
                box=ref.get('bbox')
                candidates,orientation_error=(_landing_candidates(strokes,box) if box else
                                              ([], 'MISSING_REFERENCE_BBOX'))
                chosen=candidates[0] if len(candidates)==1 else None
                cue=_adjacent_mv_cell_labels(page,chosen,box) if chosen else []
                status=('REFERENCE_VECTOR_STROKE_CANDIDATE' if chosen else
                        'AMBIGUOUS_VECTOR_STROKE' if len(candidates)>1 else
                        orientation_error or 'NO_REFERENCE_VECTOR_STROKE')
                results.append({'from_instance_key':link['from_instance_key'],
                    'to_instance_key':link['to_instance_key'],
                    'reference_side':ref['reference_side'],
                    'page':n,'source_anchor_id':ref.get('anchor_id'),
                    'reference_text':ref.get('text'),'reference_bbox':box,
                    'status':status,'vector_stroke':chosen,
                    'other_matching_strokes':candidates if len(candidates)>1 else [],
                    'adjacent_mv_line_cell_text_cue':cue,
                    'physical_device_terminal_verified':False,
                    'through_device_continuity_verified':False,
                    'feeder_membership_graph_verified':False})
            # Avoid keeping lots of PyMuPDF data alive across multi-page runs.
            del strokes, ignored, dots
    unique=sum(r['status']=='REFERENCE_VECTOR_STROKE_CANDIDATE' for r in results)
    cell=sum(bool(r['adjacent_mv_line_cell_text_cue']) for r in results)
    by_link=defaultdict(list)
    for row in results:by_link[(row['from_instance_key'],row['to_instance_key'])].append(row)
    paired=sum(len(v)==2 and all(x['status']=='REFERENCE_VECTOR_STROKE_CANDIDATE' for x in v)
               for v in by_link.values())
    return {'schema':SCHEMA,'plant_id':cross['plant_id'],
            'sld_name':path.name,
            'status':'PARTIAL_DIAGNOSTIC' if n_uninspected else 'COMPLETE_VECTOR_DIAGNOSTIC',
            'landings':results,
            'summary':{'reciprocal_documentary_links':len(cross['reciprocal_links']),
                       'reference_sides_examined':len(results),
                       'reference_sides_not_examined':n_uninspected,
                       'unique_vector_stroke_candidates':unique,
                       'with_adjacent_mv_line_cell_text_cue':cell,
                       'links_with_two_unique_stroke_candidates':paired,
                       'physical_device_terminals_verified':0,
                       'through_device_paths_verified':0,
                       'graph_verified_feeder_memberships':0},
            'policy':('Solid stroke in vicinity of a reference is only a landing candidate; '
                      'neither a nearby MV cell label nor paired strokes establish a '
                      'terminal, through-cell continuity, feeder identity, or root. '
                      'No ground truth or expected counts used. Baseline source checked '
                      'by name and page count, NOT byte-level PDF hashes.')}
