import unittest
from pathlib import Path
from sld_ci_v04_beta3.geometry.path_trace import query_pdf

FIX=Path(__file__).parent/'fixtures'
class PathTraceTests(unittest.TestCase):
    def run_case(self,name,start,end,**kwargs):
        return query_pdf(str(FIX/(name+'.pdf')),1,start,end,**kwargs)
    def test_t_junction_path(self):
        x=self.run_case('t_junction',(30,100),(150,30))
        self.assertEqual(x['status'],'PATH_FOUND');self.assertGreater(x['trace']['edge_count'],0)
        self.assertTrue(x['trace']['source_stroke_ids'])
    def test_cross_no_dot_disconnected(self):
        x=self.run_case('crossing_without_dot',(30,100),(150,30))
        self.assertEqual(x['status'],'DISCONNECTED')
    def test_cross_with_dot_connected(self):
        x=self.run_case('crossing_with_dot',(30,100),(150,30))
        self.assertEqual(x['status'],'PATH_FOUND')
    def test_short_terminal_segment(self):
        self.assertEqual(self.run_case('short_terminal_segment',(30,100),(270,100))['status'],'PATH_FOUND')
    def test_colored_conductor(self):
        self.assertEqual(self.run_case('colored_conductor',(30,100),(270,100))['status'],'PATH_FOUND')
    def test_short_gap_not_bridged(self):
        self.assertEqual(self.run_case('short_gap',(30,100),(270,100))['status'],'DISCONNECTED')
    def test_device_not_bridged(self):
        self.assertEqual(self.run_case('device_interposed',(30,100),(270,100))['status'],'DISCONNECTED')
    def test_outside_roi_is_not_verified_full_page(self):
        x=self.run_case('short_terminal_segment',(30,100),(270,100),roi=(0,0,180,200))
        self.assertEqual(x['scope'],'ROI_ONLY');self.assertFalse(x['trace']['path_verified'])
    def test_safety_cap_is_unresolved(self):
        x=self.run_case('segment_limit',(30,25),(270,25),max_strokes=2)
        self.assertEqual(x['status'],'UNRESOLVED');self.assertEqual(x['trace']['reason'],'GRAPH_INCOMPLETE')
    def test_no_anchor(self):
        self.assertEqual(self.run_case('t_junction',(12,12),(150,30))['trace']['reason'],'ANCHOR_NOT_ON_GRAPH')
    def test_dashed_is_not_connection(self):
        x=self.run_case('dashed_boundary',(30,100),(150,30))
        self.assertNotEqual(x['status'],'PATH_FOUND')
if __name__=='__main__':unittest.main()
