"""Conservative broad-phase spatial index for 2D segment bounding boxes.

No geometrical connectivity is inferred here. Each query returns a superset of
bbox-intersecting segments, including long segments that span many cells.
"""
from __future__ import annotations
from collections import defaultdict
from math import floor

class SegmentIndex:
    def __init__(self, strokes, *, cell_size=None, tolerance=0.35, max_cells_per_item=256):
        self.strokes=list(strokes)
        self.tolerance=max(0.,float(tolerance))
        if cell_size is None:
            if self.strokes:
                lengths=sorted(s.length() for s in self.strokes)
                cell_size=min(96.,max(12.,lengths[len(lengths)//2]*3))
            else:cell_size=32.
        self.cell_size=float(cell_size)
        if self.cell_size<=0:raise ValueError('cell_size must be > 0')
        self.max_cells_per_item=max_cells_per_item
        self.cells=defaultdict(set)
        self.large=set()
        for i,s in enumerate(self.strokes):
            extent=self.extent(s,self.tolerance)
            xr,yr=self._ranges(extent)
            if len(xr)*len(yr)>max_cells_per_item:
                self.large.add(i)
                continue
            for x in xr:
                for y in yr:self.cells[(x,y)].add(i)

    @staticmethod
    def extent(s, pad=0.):
        return (min(s.p1[0],s.p2[0])-pad,min(s.p1[1],s.p2[1])-pad,
                max(s.p1[0],s.p2[0])+pad,max(s.p1[1],s.p2[1])+pad)

    def _ranges(self, extent):
        x0,y0,x1,y1=extent
        return (range(floor(x0/self.cell_size),floor(x1/self.cell_size)+1),
                range(floor(y0/self.cell_size),floor(y1/self.cell_size)+1))

    def query_indices(self, s):
        xr,yr=self._ranges(self.extent(s,self.tolerance))
        # Very long queries still need an exact superset: scan the indexed
        # strokes instead of silently dropping cell combinations.
        if len(xr)*len(yr)>self.max_cells_per_item:
            return set(range(len(self.strokes)))
        result=set(self.large)
        for x in xr:
            for y in yr:result.update(self.cells.get((x,y),()))
        return result
