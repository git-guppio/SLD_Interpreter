import copy
import unittest
from sld_ci_v04_beta3.sap.hierarchy_export import (build_sap_hierarchy, REVIEW_SCHEMA)


def source(nodes, complete=True, extra_cus=0):
    return {'plant':{'plant_id':'CI::TEST'},
      'sources':{'sld':{'analysis_complete':complete},'layout':{'present':False}},
      'interpretation':{'target_hierarchy':{'nodes':nodes,'unresolved_membership':[]}},
      'target_counts':{'conversion_units':sum(x['entity_type']=='CONVERSION_UNIT' for x in nodes)+extra_cus}}


def node(id, kind, parent=None):
    return {'entity_id':id,'entity_type':kind,'parent_id':parent,'source_status':'DETECTED'}


def complete():
    return source([node('CU1','CONVERSION_UNIT'),node('CB1','IOCB','CU1'),
       node('T1','MV_LV_TRANSFORMER','CU1'),node('I1','CENTRAL_INVERTER','CU1'),
       node('A1','LV_LV_TRANSFORMER','I1'),node('S1','STRING_BOX','I1')])


def review(assets=None, links=None, plant='CI::TEST'):
    return {'schema':REVIEW_SCHEMA,'plant_id':plant,'confirmed_assets':assets or [],
            'confirmed_transformer_inverter_links':links or []}


def confirm(id,kind,parent,evidence='pdf:page1:bbox'):
    return {'asset_id':id,'entity_type':kind,'parent_id':parent,'evidence_ref':evidence}


class Alpha9SapTests(unittest.TestCase):
    def test_complete_hierarchy_has_no_tasks(self):
        r=build_sap_hierarchy(complete())
        self.assertEqual(r['status'],'HIERARCHY_STAGED_FOR_MATRIX_MAPPING')
        self.assertEqual(len(r['assets']),6)
        self.assertFalse(r['matrix_flow_import_ready'])
    def test_no_cu_requests_confirmation_not_fabrication(self):
        r=build_sap_hierarchy(source([]))
        self.assertEqual(r['plant_summary']['identified_cu_count'],0)
        self.assertEqual(r['hitl_tasks'][0]['required_type'],'CONVERSION_UNIT')
    def test_missing_category_is_unknown_not_zero_actual_assets(self):
        data=complete();data['interpretation']['target_hierarchy']['nodes']=[x for x in data['interpretation']['target_hierarchy']['nodes'] if x['entity_id']!='A1']
        r=build_sap_hierarchy(data)
        self.assertEqual(r['status'],'HITL_REQUIRED')
        self.assertTrue(any(x.get('required_type')=='LV_LV_TRANSFORMER' for x in r['hitl_tasks']))
        self.assertFalse(any(x['asset_id']=='A1' for x in r['assets']))
    def test_mixed_transformers_no_fixed_ratio(self):
        data=complete();ns=data['interpretation']['target_hierarchy']['nodes'];ns.extend([
            node('T2','MV_LV_TRANSFORMER','CU1'), node('I2','CENTRAL_INVERTER','CU1'),
            node('I3','CENTRAL_INVERTER','CU1'),node('A2','LV_LV_TRANSFORMER','I2'),
            node('A3','LV_LV_TRANSFORMER','I3'),node('S2','STRING_BOX','I2'),node('S3','STRING_BOX','I3')])
        r=build_sap_hierarchy(data)
        self.assertEqual(r['plant_summary']['counts_resolved_by_type']['MV_LV_TRANSFORMER'],2)
        self.assertEqual(r['plant_summary']['counts_resolved_by_type']['CENTRAL_INVERTER'],3)
        self.assertFalse(r['hitl_tasks'])
    def test_operator_adds_only_explicitly_confirmed(self):
        data=complete();data['interpretation']['target_hierarchy']['nodes'].pop()
        r=build_sap_hierarchy(data, review([confirm('S2','STRING_BOX','I1')]))
        self.assertFalse(r['hitl_tasks'])
        self.assertTrue([x for x in r['assets'] if x['asset_id']=='S2'][0]['operator_confirmed'])
    def test_review_must_be_same_plant(self):
        with self.assertRaises(ValueError):build_sap_hierarchy(complete(),review(plant='CI::OTHER'))
    def test_review_requires_evidence(self):
        with self.assertRaises(ValueError):build_sap_hierarchy(complete(),review([confirm('S2','STRING_BOX','I1','')]))
    def test_review_cannot_duplicate_baseline(self):
        with self.assertRaises(ValueError):build_sap_hierarchy(complete(),review([confirm('S1','STRING_BOX','I1')]))
    def test_wrong_parent_not_counted(self):
        data=complete();data['interpretation']['target_hierarchy']['nodes'][-1]['parent_id']='CU1'
        r=build_sap_hierarchy(data)
        self.assertTrue(any(t['reason']=='WRONG_PARENT_TYPE' for t in r['hitl_tasks']))
        self.assertFalse(any(x['asset_id']=='S1' for x in r['assets']))
    def test_cu_feeder_is_not_required(self):
        r=build_sap_hierarchy(complete())
        self.assertFalse(r['feeder_required_for_sap'])
        self.assertFalse(r['hitl_tasks'])
    def test_partial_source_does_not_pass(self):
        data=complete();data['sources']['sld']['analysis_complete']=False
        self.assertEqual(build_sap_hierarchy(data)['status'],'HITL_REQUIRED')
    def test_canonical_layout_cus_unmapped_reported(self):
        data=complete();data['target_counts']['conversion_units']=2
        self.assertTrue(any(x['reason']=='CANONICAL_CU_IDENTITIES_NOT_MAPPED_TO_SAP_NODES' for x in build_sap_hierarchy(data)['hitl_tasks']))
    def test_two_secondaries_one_tr_two_links(self):
        data=complete();data['interpretation']['target_hierarchy']['nodes'].extend([
            node('I2','CENTRAL_INVERTER','CU1'),node('S2','STRING_BOX','I2'),node('A2','LV_LV_TRANSFORMER','I2')])
        links=[{'transformer_id':'T1','inverter_id':'I1','secondary_index':1,'evidence_ref':'pdf:p1'},
               {'transformer_id':'T1','inverter_id':'I2','secondary_index':2,'evidence_ref':'pdf:p1'}]
        r=build_sap_hierarchy(data, review(links=links))
        self.assertEqual(len(r['transformer_inverter_associations']),2)
        self.assertEqual(r['plant_summary']['counts_resolved_by_type']['MV_LV_TRANSFORMER'],1)
    def test_repeated_secondary_cannot_connect_two_inverters(self):
        data=complete();data['interpretation']['target_hierarchy']['nodes'].extend([
            node('I2','CENTRAL_INVERTER','CU1'),node('S2','STRING_BOX','I2'),node('A2','LV_LV_TRANSFORMER','I2')])
        links=[{'transformer_id':'T1','inverter_id':i,'secondary_index':1,'evidence_ref':'pdf:p1'} for i in ('I1','I2')]
        with self.assertRaises(ValueError):build_sap_hierarchy(data,review(links=links))
    def test_out_of_scope_link_rejected(self):
        data=complete();data['interpretation']['target_hierarchy']['nodes'].extend([
            node('CU2','CONVERSION_UNIT'),node('CB2','IOCB','CU2'),node('T2','MV_LV_TRANSFORMER','CU2'),
            node('I2','CENTRAL_INVERTER','CU2'),node('S2','STRING_BOX','I2'),node('A2','LV_LV_TRANSFORMER','I2')])
        link={'transformer_id':'T1','inverter_id':'I2','secondary_index':1,'evidence_ref':'pdf:p1'}
        with self.assertRaises(ValueError):build_sap_hierarchy(data,review(links=[link]))

if __name__=='__main__':unittest.main()
