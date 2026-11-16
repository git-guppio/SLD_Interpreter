"""Alpha11 positive and negative cases: no unverified parent promoted."""
import json
import tempfile
import unittest
from pathlib import Path
from sld_ci_v04_beta3.sap.parentage_alpha11 import propose_parentage,make_draft,write_proposals,build_explicit_review
from sld_ci_v04_beta3.sap.parent_reference_alpha11 import compare_parents

P='CI::T'
CU=P+'::CU::01'
def tr(slot,x,y=175,cu=1):
    prefix=f'{P}::CU::{cu:02d}'
    return {'asset_id':f'{P}::TR::{cu:02d}.{slot:02d}',
            'type':'MV_LV_TRANSFORMER','parent_id':prefix,
            'page':1,'x':x,'y':y,'evidence_ref':f'pdf:p1:TR{slot}:xy={x},{y}'}

def inv(slot,x,y=280,cu=1,source='NATIVE_INVERTER_LABEL_CANDIDATE'):
    return {'asset_id':f'{P}::INV::{cu:02d}.{slot:02d}',
            'type':'CENTRAL_INVERTER','parent_id':None,'cu_context_id':f'{P}::CU::{cu:02d}',
            'page':1,'x':x,'y':y,'source_status':source,'evidence_ref':f'pdf:p1:I{slot}:xy={x},{y}'}

def report(*asset):return {'plant_id':P,'assets':list(asset),'source_pdf':'example.pdf'}

class Alpha11ParentTests(unittest.TestCase):
    def test_one_tr_four_inverters_no_fanout_limit(self):
        r=propose_parentage(report(tr(1,350),inv(1,308),inv(2,266),inv(3,224),inv(4,182)))
        self.assertEqual(r['summary']['spatial_parent_candidates'],4)
        self.assertEqual({z['proposed_transformer_id'] for z in r['candidates']},{f'{P}::TR::01.01'})
        self.assertEqual(r['summary']['parents_auto_confirmed_by_alpha11'],0)

    def test_two_tr_four_inverters_correct_geometric_order(self):
        r=propose_parentage(report(tr(1,350),tr(2,240),inv(1,306),inv(2,252),inv(3,198),inv(4,144)))
        self.assertEqual([z['transformer_slot'] for z in r['candidates']],[1,1,2,2])

    def test_not_overwriting_parent_id(self):
        x=inv(1,300); r=report(tr(1,350),x)
        prop=propose_parentage(r)
        self.assertIsNone(x['parent_id'])
        self.assertFalse(prop['candidates'][0]['sap_parent_confirmed'])
        self.assertFalse(prop['candidates'][0]['electrical_continuity_verified'])

    def test_no_transformer_no_candidate(self):
        z=propose_parentage(report(inv(1,308)))
        self.assertEqual(len(z['candidates']),0)
        self.assertEqual(z['unresolved'][0]['reason'],'NO_SAME_PAGE_TR_LABEL_OR_COORDINATES')

    def test_no_text_geometry_no_assets(self):
        z=propose_parentage(report())
        self.assertEqual(z['summary']['inverters_total'],0)
        self.assertEqual(z['candidates'],[])

    def test_no_cross_cu_assignment(self):
        z=propose_parentage(report(tr(1,350),inv(1,308,cu=2)))
        self.assertEqual(z['candidates'],[])

    def test_no_cross_page_assignment(self):
        x=inv(1,308);x['page']=2
        z=propose_parentage(report(tr(1,350),x))
        self.assertEqual(z['candidates'],[])

    def test_wrong_axis_not_promoted(self):
        z=propose_parentage(report(tr(1,350,y=310),inv(1,308,y=280)))
        self.assertEqual(z['candidates'],[])

    def test_nonfinite_coordinates_rejected(self):
        a=inv(1,float('nan'))
        z=propose_parentage(report(tr(1,350),a))
        self.assertEqual(z['candidates'],[])

    def test_very_far_inverter_refused(self):
        z=propose_parentage(report(tr(1,350),inv(1,40)))
        self.assertEqual(z['candidates'],[])

    def test_transformer_equal_x_ambiguous(self):
        z=propose_parentage(report(tr(1,350),tr(2,350),inv(1,308)))
        self.assertEqual(z['candidates'],[])
        self.assertEqual(z['unresolved'][0]['reason'],'OVERLAPPING_TRANSFORMER_LABEL_POSITIONS')

    def test_explicit_review_required_suggestions_not_approved(self):
        z=propose_parentage(report(tr(1,350),inv(1,308)))
        draft=make_draft(z)
        self.assertEqual(draft['confirmed_tr_inverter_groups'],[])
        self.assertEqual(draft['alpha11_suggestions_not_confirmed'][0]['status'],'SUGGESTED_NOT_CONFIRMED')

    def test_conflict_always_separate_bulk_group(self):
        z=propose_parentage(report(tr(1,350),inv(1,308),tr(1,350,cu=2),
            inv(1,308,cu=2,source='NATIVE_LABEL_CONFLICT_LOCAL_CANDIDATE')))
        self.assertEqual(len(z['suggested_hitl_groups']),2)
        self.assertTrue(any(g['printed_label_conflict_present'] for g in z['suggested_hitl_groups']))

    def test_plant_scope_does_not_globally_learn(self):
        a=propose_parentage(report(tr(1,350),inv(1,308)))
        self.assertTrue(all(c['cu_id'].startswith('CI::T::') for c in a['candidates']))
        self.assertNotIn('global_model',a)

    def test_preconfirmed_parent_is_not_second_candidate(self):
        x=inv(1,308); x['parent_id']=f'{P}::TR::01.01'
        z=propose_parentage(report(tr(1,350),x))
        self.assertEqual(z['summary']['inverters_already_confirmed'],1)
        self.assertEqual(z['candidates'],[])

    def test_outputs_review_draft_never_approved(self):
        with tempfile.TemporaryDirectory() as d:
            z=propose_parentage(report(tr(1,350),inv(1,308)))
            write_proposals(z,d)
            draft=json.loads((Path(d)/'alpha11_operator_review_DRAFT.json').read_text())
            self.assertFalse(draft['confirmed_tr_inverter_groups'])
            self.assertTrue((Path(d)/'alpha11_parent_proposals.csv').is_file())

    def test_explicit_review_builder_only_approved_groups(self):
        z=propose_parentage(report(tr(1,350),inv(1,308)))
        a=build_explicit_review(z,[])
        self.assertEqual(a['confirmed_tr_inverter_groups'],[])
        b=build_explicit_review(z,[(1,'checked:diagram:p1')])
        self.assertEqual(b['confirmed_tr_inverter_groups'][0]['inverter_slots'],[1])
        self.assertEqual(b['confirmed_tr_inverter_groups'][0]['cu_ids'],[1])
        self.assertEqual(b['schema'],'sld-sap-alpha10-reviewed-parentage/v1')

    def test_explicit_review_rejects_blank_evidence_and_invalid_indices(self):
        z=propose_parentage(report(tr(1,350),inv(1,308)))
        for values in ([(1,'')],[(2,'proof')],[(1,'ok'),(1,'ok')]):
            with self.assertRaises(ValueError):build_explicit_review(z,values)

    def test_explicit_review_rejects_forged_group(self):
        z=propose_parentage(report(tr(1,350),inv(1,308)))
        z['suggested_hitl_groups'][0]['inverter_slots']=[2]
        with self.assertRaises(ValueError):build_explicit_review(z,[(1,'operator:p1')])

    def test_reference_verification_only_post_inference(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            z=propose_parentage(report(tr(1,350),inv(1,308)))
            a=p/'pred.json'; a.write_text(json.dumps(z))
            ref=p/'gt.txt';ref.write_text('CU1 - TR1 - INV1 - SB10')
            r=compare_parents(a,ref,p/'comparison.csv')
            self.assertEqual(r['matches'],1)
            self.assertEqual(json.loads(a.read_text())['summary']['parents_auto_confirmed_by_alpha11'],0)

    def test_reference_mismatch_is_not_fixed_in_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);z=propose_parentage(report(tr(1,350),inv(1,308)))
            (p/'pred.json').write_text(json.dumps(z))
            (p/'gt.txt').write_text('CU1 - TR2 - INV1 - SB10')
            r=compare_parents(p/'pred.json',p/'gt.txt',p/'out.csv')
            self.assertEqual(r['matches'],0)
            self.assertEqual(r['mismatches'][0]['status'],'DIFFERENT_PARENT')

if __name__=='__main__':unittest.main()
