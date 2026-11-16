import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sld_ci_v04_beta3.integration.identity_tasks import plan_cu_verifications, inspect_identity_neighborhoods
from sld_ci_v04_beta3.integration.knowledge_scope import (select_scoped_knowledge,
                                                           select_scoped_feedback,stage_knowledge)
from sld_ci_v04_beta3.integration.integrated_case import _membership_provenance, assemble_report

class IdentityAndScopeTests(unittest.TestCase):
    def test_membership_layers_do_not_conflate_structural_schedule_and_graph(self):
        rec={'cu_mv_membership':[{'cu_instance_key':'1','source_status':'INFERRED','basis':'COLUMN_ALIGNMENT'},
                                  {'cu_instance_key':'2','source_status':'INFERRED','basis':'COLUMN_ALIGNMENT'}]}
        v={'explicit_schedule_membership':[{'cu_instance_key':'1'}], 'graph_verified_membership':[]}
        out=_membership_provenance(rec,v)
        self.assertEqual(out['canonical_cu_feeder_membership_count'],2)
        self.assertEqual(out['structural_inferred_count'],2)
        self.assertEqual(out['explicit_schedule_membership_count'],1)
        self.assertEqual(out['graph_verified_membership_count'],0)

    def test_queue_from_canonical_identity_without_fused_pairs(self):
        base={'plant':{'plant_id':'CI::X'},
              'source_reconciliation':{'conversion_units':[{'canonical_cu_id':'CI::X::CU::1',
                 'instance_key':'1','sld_representations':[{'page':1,'anchor_id':'a1','representation_role':'SOURCE_INSTANCE'}]}],
                 'cu_mv_membership':[{'cu_instance_key':'1','source_status':'INFERRED','mv_line_instance_key':'FEED_A'}]},
              'pages':[{'page':1,'page_type':'SLD','text_equipment_anchors':[
                  {'anchor_id':'a1','tag':'CU-1','bbox':[20,20,40,30]}],
                  'symbol_candidates':[{'text_anchor_id':'a1','evidence_state':'TEXT_ONLY','terminals':[]}]}]}
        res=plan_cu_verifications(base)
        self.assertEqual(res['summary']['canonical_cu_tasks'],1)
        self.assertEqual(res['summary']['with_sld_anchor'],1)
        self.assertEqual(res['summary']['with_same_anchor_terminal_candidate'],0)
        self.assertEqual(res['tasks'][0]['blocker'],'NO_TERMINAL_BOUND_TO_CANONICAL_CU_ANCHOR')
        self.assertEqual(res['tasks'][0]['layout_feeder_assignment']['line_key'],'FEED_A')
        self.assertFalse(res['tasks'][0]['graph_verified_feeder_membership'])

    def test_duplicate_source_anchors_never_randomly_chosen(self):
        base={'source_reconciliation':{'conversion_units':[{'canonical_cu_id':'X','instance_key':'1',
            'sld_representations':[{'page':1,'anchor_id':'A'}]}]},
            'pages':[{'page':1,'text_equipment_anchors':[{'anchor_id':'A','bbox':[0,0,1,1]},
                                                       {'anchor_id':'A','bbox':[1,1,2,2]}]}]}
        q=plan_cu_verifications(base)
        self.assertEqual(q['tasks'][0]['blocker'],'NO_SLD_CU_ANCHOR_WITH_COORDINATES')
        self.assertEqual(q['tasks'][0]['diagnostics']['NO_UNIQUE_SOURCE_ANCHOR'],1)

    def test_only_source_anchor_fused_terminals_are_candidate(self):
        base={'source_reconciliation':{'conversion_units':[{'canonical_cu_id':'X','instance_key':'1',
            'sld_representations':[{'page':1,'anchor_id':'A'}]}]},
            'pages':[{'page':1,'text_equipment_anchors':[{'anchor_id':'A','bbox':[0,0,1,1]}],
            'symbol_candidates':[{'text_anchor_id':'B','evidence_state':'FUSED',
                   'terminals':[{'point':[9,0]}],'bbox':[8,0,10,2]},
                  {'text_anchor_id':'A','evidence_state':'FUSED',
                   'terminals':[{'point':[2,0]}],'symbol_id':'S','bbox':[0,0,2,2]}]}]}
        q=plan_cu_verifications(base)
        self.assertEqual(len(q['tasks'][0]['candidate_bound_terminals']),1)
        self.assertEqual(q['tasks'][0]['candidate_bound_terminals'][0]['symbol_id'],'S')
        self.assertFalse(q['tasks'][0]['candidate_bound_terminals'][0]['electrical_role_verified'])

    def test_no_identity_tasks_does_not_open_pdf(self):
        self.assertEqual(inspect_identity_neighborhoods('fake.pdf',{'tasks':[]}),[])

    def test_same_plant_patterns_only(self):
        obj={'schema_version':2,'patterns':[
             {'pattern_type':'MV_LINE_LABEL_MAPPING','scope':'PLANT','origin_plant_id':'CI::PV8'},
             {'pattern_type':'MV_LINE_LABEL_MAPPING','scope':'PLANT','origin_plant_id':'CI::PV4'},
             {'pattern_type':'MV_LINE_LABEL_MAPPING','scope':'GENERAL'}]}
        filtered=select_scoped_knowledge(obj,'CI::PV8')
        self.assertEqual(len(filtered['patterns']),1)
        self.assertEqual(filtered['patterns'][0]['origin_plant_id'],'CI::PV8')
        self.assertEqual(len(obj['patterns']),3)

    def test_unscoped_active_operator_mapping_rejected(self):
        with self.assertRaises(ValueError):
            select_scoped_feedback([{'status':'OPERATOR_PROVIDED',
                'target':'MV_LINE_LABEL_MAPPING','value':{'X':'Linea 1'}}],'CI::PV8')
        with self.assertRaises(ValueError):
            select_scoped_feedback([{'status':'OPERATOR_PROVIDED',
                'target':'MV_LINE_LABEL_MAPPING','plant_id':'CI::PV4','value':{'X':'Linea 1'}}],'CI::PV8')

    def test_staging_never_changes_source_and_only_includes_current_plant(self):
        with TemporaryDirectory() as td:
            src=Path(td)/'original.json'
            obj={'schema_version':2,'patterns':[{'scope':'PLANT','origin_plant_id':'CI::PV8',
               'pattern_type':'MV_LINE_LABEL_MAPPING', 'mapping':{'F':'Linea 1'}},
               {'scope':'PLANT','origin_plant_id':'CI::PV4',
               'pattern_type':'MV_LINE_LABEL_MAPPING','mapping':{'F':'NOT_FOR_PV8'}}]}
            original=json.dumps(obj)
            src.write_text(original)
            paths,audit=stage_knowledge(knowledge_path=src,feedback_path=None,
                out_dir=Path(td)/'reports',sld_path='PV8_SLD.pdf',layout_path=None,plant_id='PV8')
            self.assertEqual(src.read_text(),original)
            self.assertEqual(audit['included_patterns'],1)
            self.assertEqual(audit['excluded_patterns'],1)
            self.assertEqual(json.loads(Path(paths['knowledge']).read_text())['patterns'][0]['mapping']['F'],'Linea 1')

    def test_generic_plant_queue_reports_no_false_feeder_verification(self):
        base={'plant':{'plant_id':'CI::X'},'sources':{'sld':{'analysis_complete':True},'layout':{'present':False}},
              'pages':[],'layout_pages':[],
              'source_reconciliation':{'conversion_units':[{'canonical_cu_id':'CI::X::CU::A','instance_key':'A'}],
                'cu_mv_membership':[{'cu_instance_key':'A','source_status':'INFERRED'}]}}
        r=assemble_report(base,sld_path='X.pdf')
        self.assertEqual(r['beta3_identity_verification_queue']['summary']['canonical_cu_tasks'],1)
        self.assertEqual(r['beta3_geometry']['summary']['beta3_graph_verified_feeder_membership'],0)
        self.assertEqual(r['legacy_inference']['membership_provenance']['structural_inferred_count'],1)

if __name__=='__main__':unittest.main()
