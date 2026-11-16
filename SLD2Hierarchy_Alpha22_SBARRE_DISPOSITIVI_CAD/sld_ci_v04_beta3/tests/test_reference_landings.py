import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import pymupdf
from sld_ci_v04_beta3.integration.reference_landings import _landing_candidates, analyze_reference_landings
from sld_ci_v04_beta3.geometry.kernel import Stroke

class ReferenceLandingTests(unittest.TestCase):
    box=[798.58,768.2,804.22,813.61]
    def line(self,sid,x,ystart=821.76,yend=874.2,dashed=False):
        return Stroke(sid,(x,ystart),(x,yend),None,0.24,dashed,1)
    def test_unique_vector_evidence_is_not_device_verification(self):
        xs,err=_landing_candidates([self.line('st1',800.72)],self.box)
        self.assertIsNone(err)
        self.assertEqual([x['source_stroke_id'] for x in xs],['st1'])
    def test_multiple_candidates_are_preserved_not_arbitrarily_chosen(self):
        xs,err=_landing_candidates([self.line('s1',800.72),self.line('s2',801.5)],self.box)
        self.assertEqual(len(xs),2)
    def test_dashed_never_a_conductor_evidence(self):
        xs,err=_landing_candidates([self.line('dash',800.72,dashed=True)],self.box)
        self.assertEqual(xs,[])
    def test_neighboring_text_glyph_short_strokes_excluded(self):
        xs,err=_landing_candidates([self.line('glyph',800.72,821.76,831.7)],self.box)
        self.assertEqual(xs,[])
    def test_distant_vertical_stroke_excluded(self):
        xs,err=_landing_candidates([self.line('far',825.72)],self.box)
        self.assertEqual(xs,[])
    def test_horizontal_reference_is_unresolved(self):
        xs,err=_landing_candidates([self.line('s1',801.0)],[700,800,800,810])
        self.assertEqual(xs,[])
        self.assertEqual(err,'UNSUPPORTED_REFERENCE_ORIENTATION')
    def test_invalid_baseline_identity_refuses_pdf_access(self):
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'some.pdf'
            with pymupdf.open() as d:
                d.new_page();d.save(target)
            base={'sources':{'sld':{'file_name':'other.pdf','page_count':1}}}
            with self.assertRaisesRegex(ValueError,'filename mismatch'):
                analyze_reference_landings(base,target)
    def test_incomplete_page_count_refuses_pdf(self):
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'some.pdf'
            with pymupdf.open() as d:
                d.new_page();d.save(target)
            base={'sources':{'sld':{'file_name':target.name,'page_count':2}}}
            with self.assertRaisesRegex(ValueError,'page count mismatch'):
                analyze_reference_landings(base,target)

if __name__=='__main__':unittest.main()
