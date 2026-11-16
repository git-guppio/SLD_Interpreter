import tempfile
import unittest
from pathlib import Path
from sld_ci_v04_beta3.shadow_compare import compare_pdf
from sld_ci_v04_beta3.tests.fixture_builder import generate

class ShadowCompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.dir=Path(cls.tmp.name)
        generate(cls.dir)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_read_only_comparison(self):
        pdf=self.dir/'t_junction.pdf'
        first=pdf.read_bytes()
        x=compare_pdf(pdf,pages=[1],max_strokes=1200)
        self.assertEqual(pdf.read_bytes(),first)
        self.assertFalse(x['ground_truth_used'])
        self.assertFalse(x['inference_modified'])
        self.assertEqual(x['pages'][0]['dev14c']['status'],'COMPLETE')
        self.assertEqual(x['pages'][0]['beta3']['status'],'COMPLETE')
        self.assertEqual(x['pages'][0]['comparison']['status'],'METRICS_AVAILABLE')
    def test_safety_limit_explicit(self):
        x=compare_pdf(self.dir/'segment_limit.pdf',pages=[1],max_strokes=2)
        self.assertEqual(x['status'],'PARTIAL')
        self.assertTrue(any(t['code']=='COMPARISON_INCOMPLETE' for t in x['pages'][0]['warnings']))
    def test_invalid_page(self):
        with self.assertRaises(ValueError):compare_pdf(self.dir/'t_junction.pdf',pages=[2])
