import unittest
from sld_ci_v04_beta3.geometry.roi import clip_to_roi
from sld_ci_v04_beta3.geometry.kernel import Stroke

class ROIClippingTests(unittest.TestCase):
    def test_crossing_retains_inside_and_source_id(self):
        s=Stroke('P1_D12_I2',(0,0),(10,0),None,1)
        rows,metadata=clip_to_roi([s],(2,-2,8,2))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].sid,'P1_D12_I2')
        self.assertEqual(rows[0].p1,(2.,0.))
        self.assertEqual(rows[0].p2,(8.,0.))
        self.assertEqual(metadata['counts']['CROSSING_ROI_CLIPPED'],1)
        self.assertIn('ARTIFICIAL', metadata['boundary_endpoint_policy'])
    def test_zero_intersection_rejected(self):
        s=Stroke('far',(10,10),(20,20),None,1)
        rows,meta=clip_to_roi([s],(0,0,5,5))
        self.assertEqual(rows,[])
        self.assertEqual(meta['counts']['OUTSIDE_ROI'],1)
    def test_inside_short_colored_preserved(self):
        s=Stroke('short',(1,1),(1.5,1.5),(1,0,0),0.2)
        rows,meta=clip_to_roi([s],(0,0,5,5))
        self.assertEqual(rows[0],s)
        self.assertEqual(meta['counts']['FULLY_INSIDE_ROI'],1)
    def test_side_touch_no_false_segment(self):
        s=Stroke('touch',(-1,0),(0,0),None,1)
        rows,meta=clip_to_roi([s],(0,0,5,5))
        self.assertEqual(rows,[])
    def test_diagonal_clips_two_boundaries(self):
        s=Stroke('diag',(-1,-1),(6,6),None,1)
        rows,meta=clip_to_roi([s],(0,0,5,5))
        self.assertEqual(rows[0].p1,(0.,0.))
        self.assertEqual(rows[0].p2,(5.,5.))
        self.assertEqual(meta['counts']['CROSSING_ROI_CLIPPED'],1)

if __name__=='__main__': unittest.main()
