import unittest
from sld_ci_v04_beta3.geometry.kernel import Stroke
from sld_ci_v04_beta3.geometry.classify import classify_strokes

class ClassificationTests(unittest.TestCase):
    def test_exact_duplicate_reversed(self):
        a=Stroke('a',(0,0),(9,0),(0,0,0),1)
        b=Stroke('b',(9,0),(0,0),(0,0,0),1)
        out, audit=classify_strokes([a,b])
        self.assertEqual(len(out),1)
        self.assertEqual(audit['counts']['EXACT_DUPLICATE'],1)
    def test_short_colored_diagonal_preserved(self):
        a=Stroke('a',(0,0),(0.2,0.3),(0,1,0),1)
        out,audit=classify_strokes([a])
        self.assertEqual(len(out),1)
        self.assertEqual(audit['counts']['SHORT_UNDER_8PT_RETAINED'],1)
        self.assertEqual(audit['counts']['COLORED_RETAINED'],1)
    def test_scope_roi_excludes_crossing_boundary(self):
        a=Stroke('a',(2,2),(8,2),(0,0,0),1)
        b=Stroke('b',(8,3),(12,3),(0,0,0),1)
        out,audit=classify_strokes([a,b],roi=(0,0,10,10))
        self.assertEqual(len(out),1)
        self.assertEqual(audit['completion_scope'],'ROI_ONLY')
    def test_dashed_excluded_with_reason(self):
        a=Stroke('a',(0,0),(10,0),(0,0,0),1,True)
        out,audit=classify_strokes([a])
        self.assertEqual(out,[])
        self.assertEqual(audit['counts']['DASHED_GRAPHIC'],1)
    def test_nearby_distinct_segments_not_merged(self):
        a=Stroke('a',(0,0),(10,0),None,1)
        b=Stroke('b',(0.01,0),(10,0),None,1)
        out,_=classify_strokes([a,b])
        self.assertEqual(len(out),2)
if __name__=='__main__':unittest.main()
