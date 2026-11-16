"""Clip vector segments into an ROI without inventing electrical connectivity.

Unlike naive endpoint containment, this retains the portion of a conductor
that crosses the diagnostic ROI boundary. Every clipped segment retains its
original PDF source stroke ID, and the report records artificial cuts.

An ROI edge is an artificial sampling boundary, NEVER a physical conductor
terminal or end-to-end connectivity proof.
"""
from __future__ import annotations
from dataclasses import replace
from collections import Counter
from .kernel import Stroke


def clip_to_roi(strokes:list[Stroke], roi:tuple[float,float,float,float]):
    if len(roi)!=4 or roi[0]>=roi[2] or roi[1]>=roi[3]:
        raise ValueError('invalid ROI')
    x0,y0,x1,y1=roi
    out=[];counts=Counter(); clipped=[]
    for s in strokes:
        (ax,ay),(bx,by)=s.p1,s.p2
        dx=bx-ax;dy=by-ay
        lo,hi=0.,1.
        excluded=False
        for p,q in ((-dx,ax-x0),(dx,x1-ax),(-dy,ay-y0),(dy,y1-ay)):
            if abs(p)<1e-12:
                if q < 0:excluded=True;break
                continue
            t=q/p
            if p<0:lo=max(lo,t)
            else:hi=min(hi,t)
            if lo>hi:excluded=True;break
        if excluded or hi < lo or hi-lo<1e-10:
            counts['OUTSIDE_ROI']+=1
            continue
        a=(ax+lo*dx,ay+lo*dy);b=(ax+hi*dx,ay+hi*dy)
        if max(abs(a[0]-b[0]),abs(a[1]-b[1]))<1e-9:
            counts['DEGENERATE_CLIP']+=1
            continue
        cut=(lo>1e-9 or hi<1-1e-9)
        if cut:
            counts['CROSSING_ROI_CLIPPED']+=1
            if len(clipped)<20:
                clipped.append({'sid':s.sid,'clipped_start':lo>1e-9,
                                'clipped_end':hi<1-1e-9,
                                'inside_p1':list(a),'inside_p2':list(b)})
        else:
            counts['FULLY_INSIDE_ROI']+=1
        out.append(replace(s,p1=a,p2=b))
    counts['RETAINED_AFTER_ROI_CLIPPING']=len(out)
    return out, {'counts':dict(counts),'boundary_clipped_samples':clipped,
                 'boundary_endpoint_policy':'ARTIFICIAL_DIAGNOSTIC_NOT_ELECTRICAL_TERMINAL'}
