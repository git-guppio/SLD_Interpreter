import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from sld_ci_v04_beta3.integration.auto_pair import eligible_symbols,plan_pairs,pair_path,inspect_pair
from sld_ci_v04_beta3.integration.integrated_case import (
  _indexes, cross_source_occurrences, summarize_legacy,assemble_report)
from sld_ci_v04_beta3.geometry.kernel import Stroke,build_graph


def fused(symbol_id,tag,box, terminals=1):
    return {'symbol_id':symbol_id,'tag':tag,'bbox':list(box),
            'candidate_type':'ELECTRICAL_SYMBOL_CANDIDATE',
            'evidence_state':'FUSED','terminals':[
               {'point':list((box[2],(box[1]+box[3])/2))} for _ in range(terminals)]}

class IntegratedCaseTests(unittest.TestCase):
    def test_does_not_promote_text_only_or_unbound(self):
        p={'symbol_candidates':[fused('one','A',(0,0,2,2)),
              {**fused('two','B',(10,0,12,2)),'evidence_state':'TEXT_ONLY'},
              {**fused('three','C',(20,0,22,2)),'terminals':[]}]}
        self.assertEqual([x['tag'] for x in eligible_symbols(p)],['A'])
        self.assertEqual(plan_pairs(p),[])
    def test_pair_order_is_geometric_not_plant_specific(self):
        p={'page_width_pt':100,'page_height_pt':100,
           'symbol_candidates':[fused('a','F1',(0,0,2,2)),
           fused('b','F2',(10,0,12,2)),fused('c','F3',(65,0,67,2))]}
        self.assertEqual(len(plan_pairs(p)),1)
        self.assertEqual([x['tag'] for x in plan_pairs(p)[0]],['F1','F2'])
    def test_path_provides_stroke_evidence_not_electrical_verification(self):
        a=fused('a','T1',(-2,-2,0,2)); a['terminals']=[{'point':[0,0]}]
        b=fused('b','T2',(10,-2,12,2)); b['terminals']=[{'point':[10,0]}]
        g=build_graph([Stroke('stroke1',(0,0),(10,0),None,1)],max_strokes=10)
        r=pair_path(g,a,b)
        self.assertEqual(r['status'],'LOCAL_GEOMETRIC_PATH_CANDIDATE')
        self.assertEqual(r['path']['source_stroke_ids'],['stroke1'])
        self.assertFalse(r['verified_electrical'])
    def test_artificial_roi_boundary_is_not_verified_continuity(self):
        a=fused('a','T1',(-2,-2,0,2));a['terminals']=[{'point':[0,0]}]
        b=fused('b','T2',(10,-2,12,2));b['terminals']=[{'point':[10,0]}]
        g=build_graph([Stroke('one',(0,0),(10,0),None,1)],max_strokes=10)
        r=pair_path(g,a,b,roi=(0,-3,10,3))
        self.assertEqual(r['status'],'UNRESOLVED')
        self.assertEqual(r['reason'],'PATH_TOUCHES_ARTIFICIAL_ROI_BOUNDARY')
    def test_device_body_never_auto_bridged(self):
        a=fused('a','T1',(4,-1,6,1));a['terminals']=[{'point':[4,0]}]
        b=fused('b','T2',(8,-1,10,1));b['terminals']=[{'point':[8,0]}]
        g=build_graph([Stroke('through',(4,0),(8,0),None,1)],max_strokes=10)
        r=pair_path(g,a,b)
        self.assertNotEqual(r['status'],'LOCAL_GEOMETRIC_PATH_CANDIDATE')
    def test_short_gap_does_not_bridge(self):
        a=fused('a','T1',(-2,-2,0,2));a['terminals']=[{'point':[0,0]}]
        b=fused('b','T2',(10,-2,12,2));b['terminals']=[{'point':[10,0]}]
        g=build_graph([Stroke('part_a',(0,0),(4,0),None,1),
                       Stroke('part_b',(5,0),(10,0),None,1)],max_strokes=10)
        self.assertEqual(pair_path(g,a,b)['status'],'DISCONNECTED_IN_ROI')
    def test_reject_safety_cap(self):
        a=fused('a','T1',(-2,-2,0,2));b=fused('b','T2',(10,-2,12,2))
        self.assertEqual(pair_path({'status':'INCOMPLETE'},a,b)['status'],'UNRESOLVED')
    def test_tag_match_is_candidate_never_assertion(self):
        s=[{'page':1,'page_type':'SLD','text_equipment_anchors':[{
                 'tag':'CABINA 7','anchor_role':'INSTANCE','anchor_id':'s',
                 'equipment_type':'CONVERSION_UNIT','bbox':[1,2,3,4]}]}]
        l=[{'page':1,'page_type':'LAYOUT','text_equipment_anchors':[{
                 'tag':'cabina  7','anchor_role':'INSTANCE','anchor_id':'l',
                 'equipment_type':'CONVERSION_UNIT','bbox':[1,2,3,4]}]}]
        out=cross_source_occurrences(s,l)
        self.assertEqual(len(out),1)
        self.assertFalse(out[0]['identity_verified_by_tag_only'])
        self.assertTrue(out[0]['unique_both_sources'])
    def test_repeated_tag_not_arbitrarily_selected(self):
        a={'tag':'CABINA 7','anchor_role':'INSTANCE','anchor_id':'s','bbox':[1,2,3,4]}
        s=[{'page':1,'text_equipment_anchors':[a,a]}]
        l=[{'page':1,'text_equipment_anchors':[a]}]
        self.assertFalse(cross_source_occurrences(s,l)[0]['unique_both_sources'])
    def test_no_global_mapping_or_gt_lookups(self):
        base={'plant':{'plant_id':'UNKNOWN_NEW_PLANT'},
              'sources':{'sld':{'analysis_complete':True},'layout':{'present':False}},
              'pages':[],'layout_pages':[],
              'target_counts':{'conversion_units':2},
              'feeder_verification':{'summary':{'explicit_schedule_membership_count':1,
                      'graph_verified_cu_mv_membership_count':0}},
              'source_reconciliation':{'summary':{'canonical_conversion_unit_count':2}}}
        with TemporaryDirectory() as td:
            report=assemble_report(base,sld_path=str(Path(td)/'new.pdf'))
        self.assertFalse(report['ground_truth_used'])
        self.assertFalse(report['expected_counts_used'])
        self.assertEqual(report['legacy_inference']['target_counts']['conversion_units'],2)
        self.assertEqual(report['beta3_geometry']['summary']['beta3_graph_verified_feeder_membership'],0)
        self.assertEqual(report['beta3_geometry']['summary']['inspections_completed'],0)
    def test_processed_page_incomplete_is_reported(self):
        base={'plant':{'plant_id':'X'},'pages':[{'page_type':'ERROR','page':1,'error':'bad PDF'}],
              'sources':{'sld':{'analysis_complete':False},'layout':{'present':False}}}
        r=assemble_report(base,sld_path='X.pdf')
        self.assertEqual(r['status'],'PARTIAL')
        self.assertEqual(r['beta3_geometry']['error_diagnostics'][0]['reason'],'DEV14C_PAGE_ERROR')

if __name__=='__main__':unittest.main()
