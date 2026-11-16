import json, tempfile, unittest
from pathlib import Path
from sld_ci_v04_beta3.geometry.kernel import analyze_pdf
from sld_ci_v04_beta3.tests.fixture_builder import generate

class PdfGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.dir=Path(cls.tmp.name)
        generate(cls.dir)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def run_case(self,name,**kwargs):return analyze_pdf(self.dir/(name+'.pdf'),**kwargs)
    def test_crossing_without_dot(self):
        x=self.run_case('crossing_without_dot')
        self.assertEqual(x['component_count'],2)
        self.assertTrue(any(not v['connected'] for v in x['crossings']))
    def test_crossing_with_dot(self):
        x=self.run_case('crossing_with_dot')
        self.assertEqual(x['component_count'],1)
        self.assertTrue(any(v['evidence']=='JUNCTION_DOT' for v in x['crossings']))
    def test_t_junction(self):
        self.assertEqual(self.run_case('t_junction')['component_count'],1)
    def test_short_segment_retained(self):
        x=self.run_case('short_terminal_segment')
        self.assertEqual(x['component_count'],1)
        self.assertEqual(x['strokes'],3)
    def test_colored_conductor(self):
        self.assertEqual(self.run_case('colored_conductor')['component_count'],1)
    def test_dashed_boundary_not_electrical(self):
        x=self.run_case('dashed_boundary')
        self.assertEqual(x['component_count'],1)
        self.assertTrue(any(d['reason']=='DASHED_NON_CONDUCTIVE_CANDIDATE' for d in x['ignored_drawings']))
    def test_device_not_auto_bridged(self):
        self.assertEqual(self.run_case('device_interposed')['component_count'],2)
    def test_short_gap_unresolved(self):
        self.assertEqual(self.run_case('short_gap')['component_count'],2)
    def test_thick_busbar(self):
        self.assertEqual(self.run_case('thick_busbar')['component_count'],1)
    def test_diagonal(self):
        self.assertEqual(self.run_case('diagonal_conductor')['component_count'],1)
    def test_limit_explicit(self):
        x=analyze_pdf(self.dir/'segment_limit.pdf',max_strokes=3)
        self.assertEqual(x['status'],'INCOMPLETE')
        self.assertEqual(x['warnings'][0]['code'],'SEGMENT_LIMIT')
