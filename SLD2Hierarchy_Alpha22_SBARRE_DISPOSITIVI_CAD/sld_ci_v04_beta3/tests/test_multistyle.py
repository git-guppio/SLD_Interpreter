"""Alpha5: plant-neutral classification and strict evidence boundaries."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pymupdf
from sld_ci_v04_beta3.integration.multistyle import (
    classify_page_lines,audit_multistyle,_ocr_preview,_roi_from_box,
)

class MultistyleTests(unittest.TestCase):
    def row(self,t,box=(20,20,120,40)):
        return {'text':t,'bbox':list(box)}
    def test_matchline_is_not_electrical_continuation(self):
        refs,dev=classify_page_lines([self.row('MATCHLINE (SEE E-136A)')],12)
        self.assertEqual(refs[0]['reference_kind'],'GRAPHIC_MATCHLINE_UNQUALIFIED')
        self.assertEqual(refs[0]['sheet_id_candidates'],['E-136A'])
        self.assertFalse(refs[0]['electrical_connection_verified'])
        self.assertFalse(refs[0]['reciprocal_reference_verified'])
        self.assertFalse(dev)
    def test_sheet_note_is_documentary_only(self):
        refs,_=classify_page_lines([self.row('2. SEE SHEET E-221 FOR CABLE SIZES')],3)
        self.assertEqual(refs[0]['reference_kind'],'DRAWING_POINTER_NOT_ELECTRICAL')
        self.assertEqual(refs[0]['sheet_id_candidates'],['E-221'])
    def test_external_company_drawing_number_not_fake_sheet_id(self):
        refs,_=classify_page_lines([self.row('VER PLANO UNIFILAR MT REF. GRE.EEC.D.24.ES.P.18028.00.073.00')],1)
        self.assertEqual(refs[0]['reference_kind'],'DRAWING_POINTER_NOT_ELECTRICAL')
        self.assertEqual(refs[0]['sheet_id_candidates'],[])
    def test_subcampo_reference_still_only_a_candidate(self):
        refs,_=classify_page_lines([self.row('A SUBCAMPO 4')],2)
        self.assertEqual(refs[0]['reference_kind'],'CU_CONTINUATION_UNPAIRED')
        self.assertFalse(refs[0]['electrical_connection_verified'])
    def test_repeated_equipment_tags_keep_provenance(self):
        refs,d=classify_page_lines([self.row('NNB-TPO-02-01'),self.row('NNB-TPO-02-01',(40,50,100,70))],1)
        self.assertEqual([x['tag_type'] for x in d],['TRANSFORMER_TAG']*2)
        self.assertNotEqual(d[0]['bbox'],d[1]['bbox'])
        self.assertFalse(refs)
    def test_no_generic_transformer_counted_as_named_equipment(self):
        r,d=classify_page_lines([self.row('TRANSFORMADOR')],1)
        self.assertFalse(d)
    def test_tag_embedded_in_long_note_not_instance(self):
        r,d=classify_page_lines([self.row('SEE SHEET E-400 WITH XFR-10')],1)
        self.assertFalse(d)
    def test_crop_roi_stays_inside_page(self):
        roi=_roi_from_box([5,5,12,12],[0,0,100,100],65)
        self.assertEqual(list(roi),[0,0,77,77])
    def _pdf(self,pages):
        doc=pymupdf.open()
        for specs in pages:
            page=doc.new_page(width=600,height=500)
            for text,x,y in specs:
                page.insert_text((x,y),text,fontsize=10)
                page.draw_line((x,y+25),(x+90,y+25),width=1)
        return doc
    def test_local_tags_enable_geometry_on_same_page(self):
        with TemporaryDirectory() as tmp:
            name=Path(tmp)/'example.pdf'
            with self._pdf([[('IBR-TPO-01-02',150,190)]]) as d:d.save(name)
            r=audit_multistyle(name,max_probe_pages=1,regions_per_page=1)
            self.assertEqual(r['summary']['pages_with_named_equipment'],1)
            self.assertEqual(r['summary']['local_vector_review_regions'],1)
            probe=r['pages'][0]['local_vector_reviews'][0]
            self.assertEqual(probe['tag'],'IBR-TPO-01-02')
            self.assertGreater(probe['solid_line_segments_overlapping_roi'],0)
            self.assertFalse(probe['terminal_bound'])
            self.assertFalse(probe['path_verified'])
            self.assertEqual(r['summary']['graph_verified_feeder_memberships'],0)
    def test_page_without_text_is_ocr_eligible_without_ocr(self):
        with TemporaryDirectory() as tmp:
            name=Path(tmp)/'empty.pdf'
            with pymupdf.open() as d:d.new_page();d.save(name)
            r=audit_multistyle(name)
            self.assertEqual(r['summary']['pages_without_native_text'],1)
            self.assertEqual(r['summary']['pages_ocr_attempted'],0)
            self.assertEqual(r['pages'][0]['ocr_preview']['status'],'NOT_REQUESTED')
    def test_optional_ocr_unavailable_safe(self):
        with pymupdf.open() as d:
            p=d.new_page()
            with patch('sld_ci_v04_beta3.integration.multistyle.shutil.which', return_value=None):
                r=_ocr_preview(p)
            self.assertEqual(r['status'],'DEPENDENCY_UNAVAILABLE')
    def test_sample_budget_never_claims_full_coverage(self):
        with TemporaryDirectory() as tmp:
            name=Path(tmp)/'case.pdf'
            with self._pdf([[('NNB-TPO-01-01',100,100)],[('NNB-TPO-01-02',100,100)]]) as d:d.save(name)
            r=audit_multistyle(name,max_pages=1)
            self.assertEqual(r['status'],'PARTIAL_PAGE_SAMPLE')
            self.assertEqual(r['source']['page_count'],2)
    def test_roi_drawing_cap_safely_declines(self):
        with TemporaryDirectory() as tmp:
            name=Path(tmp)/'case.pdf'
            with self._pdf([[('NNB-TPO-01-01',100,100)]]) as d:d.save(name)
            r=audit_multistyle(name,max_drawings=0)
            self.assertEqual(r['pages'][0]['geometry_status'],'DRAWING_COMPLEXITY_SAFETY_CAP')
            self.assertEqual(r['summary']['local_vector_review_regions'],0)
    def test_matchline_and_tag_do_not_create_connection(self):
        with TemporaryDirectory() as tmp:
            name=Path(tmp)/'case.pdf'
            with self._pdf([[('MATCHLINE (SEE E-231)',100,120),('XFR-48',100,220)]]) as d:d.save(name)
            r=audit_multistyle(name)
            self.assertIn('MATCHLINE_DOCUMENTARY_UNQUALIFIED',r['pages'][0]['modes'])
            self.assertIn('LOCAL_TAGGED_EQUIPMENT',r['pages'][0]['modes'])
            self.assertEqual(r['summary']['cross_sheet_electrical_links_verified'],0)
            self.assertEqual(r['summary']['through_device_paths_verified'],0)

if __name__=='__main__': unittest.main()
