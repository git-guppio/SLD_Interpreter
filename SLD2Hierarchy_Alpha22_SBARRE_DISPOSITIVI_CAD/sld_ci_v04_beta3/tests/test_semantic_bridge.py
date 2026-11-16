import tempfile
import unittest
from pathlib import Path
import pymupdf as fitz

from sld_ci_v04_beta3.integration.semantic_bridge import (
    inspect_page, choose_unique_tag_roi, _enters_body, _external_adjacency, _nearest_node,
)


def sample(path, *,label='XX-INV-01-01', put_device=True, through_body=False, colored=False):
    doc=fitz.open(); page=doc.new_page(width=340,height=210)
    col=(0,0,1) if colored else (0,0,0)
    def draw_line(a,b):
        sh=page.new_shape();sh.draw_line(a,b);sh.finish(color=col,width=1);sh.commit()
    if through_body:
        draw_line((20,100),(300,100))
    else:
        draw_line((20,100),(145,100))
        draw_line((165,100),(300,100))
    if put_device:
        sh=page.new_shape();sh.draw_rect(fitz.Rect(145,91,165,109));sh.finish(color=(0,0,0));sh.commit()
    if label:page.insert_text((171,99),label,fontsize=9)
    doc.save(str(path),garbage=4,deflate=True);doc.close()

class SemanticBridgeTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        self.p=self.root/'A.pdf';sample(self.p)
    def tearDown(self):self.t.cleanup()
    def audit(self,**kwargs):return inspect_page(self.p,1,**kwargs)

    def test_native_semantic_anchors_not_auto_assets(self):
        r=self.audit()
        self.assertEqual(r['status'],'COMPLETE_DIAGNOSTIC')
        a=[x for x in r['text']['semantic_anchors'] if x['tag']=='XX-INV-01-01']
        self.assertTrue(a)
        self.assertEqual(a[0]['connection_status'],'TEXT_ONLY')
        self.assertEqual(r['feeder_graph_verified_membership'],[])
        self.assertEqual(r['feeder_documental_membership'],[])
    def test_fuses_text_with_vector_and_terminals(self):
        r=self.audit()
        syms=[s for s in r['symbols'] if s['tag']=='XX-INV-01-01' and s['evidence_state']=='FUSED']
        self.assertTrue(syms, r['symbols'][:3])
        self.assertGreaterEqual(len(syms[0]['terminals']),2)
        self.assertEqual(syms[0]['status'],'CANDIDATE_NOT_ACCEPTED_AS_ASSET')
    def test_operator_feeder_root_to_named_device_terminal(self):
        r=self.audit(feeder_point=(20,100),feeder_label='Linea TEST',plant_id='UNKNOWN-PLANT')
        matching=[t for t in r['traces'] if t['status']=='LOCAL_GEOMETRIC_PATH_CANDIDATE']
        self.assertTrue(matching,r['traces'])
        self.assertEqual(matching[0]['target_tag'],'XX-INV-01-01')
        self.assertTrue(matching[0]['path']['source_stroke_ids'])
        self.assertFalse(matching[0]['verified_electrical'])
        self.assertFalse(matching[0]['feeder_membership_asserted'])
    def test_requires_plant_scope_on_operator_feeder(self):
        with self.assertRaises(ValueError):self.audit(feeder_point=(20,100))
    def test_label_without_coordinates_is_invalid(self):
        with self.assertRaises(ValueError):self.audit(feeder_label='Linea',plant_id='A')
    def test_plain_text_tag_not_enough_to_bridge_equipment(self):
        q=self.root/'B.pdf';sample(q,put_device=False)
        r=inspect_page(q,feeder_point=(20,100),plant_id='A')
        self.assertFalse([x for x in r['symbols'] if x['evidence_state']=='FUSED'])
        self.assertTrue(r['traces'])
        self.assertEqual(r['traces'][0]['status'],'UNRESOLVED')
    def test_blocks_passage_through_entire_device(self):
        self.assertTrue(_enters_body((20,100),(300,100),(140,85,180,115)))
        self.assertFalse(_enters_body((20,100),(140,100),(140,85,180,115)))
        a,blocked=_external_adjacency({'edges':[{'from':[20,100],'to':[300,100],'source_sid':'bad'}]},[(140,85,180,115)])
        self.assertFalse(a);self.assertEqual(blocked,['bad'])
    def test_roi_never_full_page(self):
        r=self.audit(roi=(0,70,225,135))
        self.assertEqual(r['scope'],'ROI_ONLY')
        self.assertFalse(r['feeder_graph_verified_membership'])
    def test_safety_cap_reports_semantics_only(self):
        r=self.audit(max_strokes=1,feeder_point=(20,100),plant_id='A')
        self.assertEqual(r['status'],'INCOMPLETE');self.assertTrue(r['text']['anchor_count'])
        self.assertFalse(r['symbols']);self.assertFalse(r['feeder_graph_verified_membership'])
    def test_ambiguous_closest_node(self):
        a={(0.,0.):[],(1.,0.):[]}
        self.assertEqual(_nearest_node((.5,0),a,1)[1],'AMBIGUOUS_FEEDER_ANCHOR')
    def test_colored_feed_line_keeps_terminals(self):
        q=self.root/'Colored.pdf';sample(q,colored=True)
        r=inspect_page(q,feeder_point=(20,100),plant_id='A')
        self.assertTrue(r['text']['anchor_count'])
        self.assertGreater(r['geometry']['retained_candidates'],0)
    def test_unique_tag_auto_roi_is_diagnostic_only(self):
        roi,selection=choose_unique_tag_roi(self.p,1,'XX-INV-01-01',padding=60)
        self.assertEqual(selection['tag'],'XX-INV-01-01')
        r=self.audit(roi=roi)
        self.assertEqual(r['scope'],'ROI_ONLY')
        self.assertFalse(r['feeder_graph_verified_membership'])
    def test_unknown_tag_refused_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError,'found 0'):
            choose_unique_tag_roi(self.p,1,'NOT-FOUND')
    def test_operator_plant_scope_never_reused_between_runs(self):
        first=self.audit(feeder_point=(20,100),feeder_label='Linea TEST',plant_id='PLANT-ONE')
        second=self.audit(feeder_point=(20,100),feeder_label='Linea OTHER',plant_id='PLANT-TWO')
        one=first['traces'][0]
        two=second['traces'][0]
        self.assertEqual(one['operator_plant_id'],'PLANT-ONE')
        self.assertEqual(two['operator_plant_id'],'PLANT-TWO')
        self.assertEqual(two['operator_feeder_label'],'Linea OTHER')
        self.assertNotIn('PLANT-ONE',str(second))
    def test_duplicate_tags_refused_as_ambiguous_roi(self):
        q=self.root/'Double.pdf'
        sample(q)
        with fitz.open(q) as doc:
            pg=doc[0]
            pg.insert_text((180,160),'XX-INV-01-01',fontsize=9)
            doc.save(str(self.root/'Double2.pdf'))
        with self.assertRaisesRegex(ValueError,'found 2'):
            choose_unique_tag_roi(self.root/'Double2.pdf',1,'XX-INV-01-01')
    def test_no_ground_truth_inputs_to_engine(self):
        r=self.audit()
        self.assertFalse(r['ground_truth_used']);self.assertFalse(r['expected_counts_used'])
        self.assertFalse(r['case_output_modified']);self.assertFalse(r['dev14c_modified'])

if __name__=='__main__':unittest.main()
