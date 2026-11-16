"""Flag repeated short dash-like strokes without joining them electrically."""
from __future__ import annotations
from collections import defaultdict
from math import hypot


def find_microdash_candidates(strokes, *, max_dash_length=7., min_members=4,
                              angle_tolerance=0.075, lane_tolerance=0.8):
    """Detect repeated short *separate* collinear strokes for human review.

    Each result is only a graphic-pattern candidate, never conductor evidence;
    none of the input strokes are removed or joined.
    """
    lanes=defaultdict(list)
    for s in strokes:
        dx=s.p2[0]-s.p1[0]; dy=s.p2[1]-s.p1[1]
        ln=hypot(dx,dy)
        if not 0.05<=ln<=max_dash_length:continue
        if abs(dy)<=angle_tolerance*ln:
            lane=('H',round((s.p1[1]+s.p2[1])/2/lane_tolerance))
            a,b=sorted((s.p1[0],s.p2[0]))
        elif abs(dx)<=angle_tolerance*ln:
            lane=('V',round((s.p1[0]+s.p2[0])/2/lane_tolerance))
            a,b=sorted((s.p1[1],s.p2[1]))
        else:continue
        lanes[lane].append((a,b,s.sid))
    found=[]
    for lane,items in lanes.items():
        items.sort()
        runs=[];run=[]
        for item in items:
            if run:
                previous=run[-1]
                gap=item[0]-previous[1]
                # Only a real space between disjoint strokes; touching micro
                # segments must NOT be treated as a dashed pattern.
                if not (0.15<=gap<=max_dash_length*2):
                    if len(run)>=min_members:runs.append(run)
                    run=[]
            run.append(item)
        if len(run)>=min_members:runs.append(run)
        for run in runs:
            gaps=[run[j+1][0]-run[j][1] for j in range(len(run)-1)]
            median=sorted(gaps)[len(gaps)//2]
            # Mild regularity control; allows minor drafting noise.
            if median<=0 or max(abs(g-median) for g in gaps)>max(0.6,0.5*median):continue
            found.append({'axis':lane[0],'stroke_ids':[v[2] for v in run],
                          'median_gap_pt':round(median,3),
                          'classification':'MICRO_DASH_PATTERN_CANDIDATE',
                          'electrical_continuity_verified':False})
    return found
