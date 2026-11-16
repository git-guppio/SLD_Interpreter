"""Document-agnostic vector candidate classification and exact normalization.

A conservative inventory, not an electrical connectivity assertion. No PDF names,
asset counts, learned plant mappings or regression oracles are consulted.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
from .kernel import Stroke


def _same_segment_key(s: Stroke, precision=4):
    a=tuple(round(c,precision) for c in s.p1)
    b=tuple(round(c,precision) for c in s.p2)
    return tuple(sorted((a,b))), s.color, round(s.width,3), s.dashed


def classify_strokes(strokes: list[Stroke], *, roi: tuple[float,float,float,float]|None=None):
    """Conservatively filter only proven non-usable items and duplicates.

    ROI is an explicit diagnostic scope; never describe ROI graph as a full-page graph.
    Preserve short, colored and angled strokes for later contextual interpretation.
    """
    counts=Counter(); excluded=[]; candidates=[]; seen={}; duplicate_samples=[]
    for s in strokes:
        if roi is not None:
            x0,y0,x1,y1=roi
            # containment avoids interpreting cropped conductor ends as junctions
            if not (x0<=s.p1[0]<=x1 and y0<=s.p1[1]<=y1 and
                    x0<=s.p2[0]<=x1 and y0<=s.p2[1]<=y1):
                counts['OUTSIDE_ROI_OR_BOUNDARY_CROSSING']+=1
                continue
        if s.dashed:
            counts['DASHED_GRAPHIC']+=1
            excluded.append({'sid':s.sid,'reason':'DASHED_GRAPHIC'})
            continue
        if s.length() <= 1e-7:
            counts['ZERO_LENGTH']+=1
            excluded.append({'sid':s.sid,'reason':'ZERO_LENGTH'})
            continue
        k=_same_segment_key(s)
        if k in seen:
            counts['EXACT_DUPLICATE']+=1
            if len(duplicate_samples)<12: duplicate_samples.append({'sid':s.sid,'identical_to':seen[k]})
            continue
        seen[k]=s.sid
        candidates.append(s)
    counts['CANDIDATES_RETAINED']=len(candidates)
    counts['SHORT_UNDER_8PT_RETAINED']=sum(s.length()<8 for s in candidates)
    counts['COLORED_RETAINED']=sum(s.color is not None and (max(s.color)-min(s.color)>0.1) for s in candidates)
    return candidates, {'raw_strokes':len(strokes),'counts':dict(counts),
                        'exclusion_samples':excluded[:12], 'duplicate_samples':duplicate_samples,
                        'roi':list(roi) if roi else None,
                        'policy':'CONSERVATIVE_INVENTORY_NO_SEMANTIC_CONDUCTOR_CLAIM',
                        'completion_scope':'ROI_ONLY' if roi else 'FULL_PAGE_CANDIDATE_INVENTORY'}
