"""No plant-specific grouping oracle: data below are synthetic documents."""
import unittest
from copy import deepcopy
from sld_ci_v04_beta3.integration.cross_sheet import analyze_cross_sheet


def _base():
    plant='CI::SYNTH'
    return {'plant': {'plant_id':plant},
        'source_reconciliation':{
            'conversion_units':[
                {'instance_key':key,'canonical_cu_id':f'{plant}::CU::{key}',
                 'sld_representations':[{'page':page,'representation_role':'SOURCE_INSTANCE'}]}
                for page,key in [(2,'alpha'), (3,'beta'), (4,'gamma')]],
            'cu_mv_membership':[
                {'cu_instance_key':key,'mv_line_instance_key':'FEEDER_X',
                 'source_status':'INFERRED'} for key in ['alpha','beta','gamma']]},
        'pages':[
            {'page':2,'text_equipment_anchors':[_ref('R1','TO CONVERSION UNIT beta','beta',2)]},
            {'page':3,'text_equipment_anchors':[
                _ref('R2','FROM CONVERSION UNIT alpha','alpha',3),
                _ref('R3','TO CONVERSION UNIT gamma','gamma',3)]},
            {'page':4,'text_equipment_anchors':[_ref('R4','FROM CONVERSION UNIT beta','beta',4)]}]}


def _ref(anchor_id,text,target,page):
    return {'anchor_role':'REFERENCE','anchor_id':anchor_id,'text':text,
        'page':page,'tag':f'CU {target}','bbox':[20,30,35,48],
        'source':'NATIVE_PDF_TEXT',
        'attributes':{'representation_role':'CROSS_SHEET_REFERENCE','instance_hint':target}}


class CrossSheetTests(unittest.TestCase):
    def test_reciprocal_pairs_form_documentary_groups_only(self):
        out=analyze_cross_sheet(_base())
        self.assertEqual(out['summary']['reciprocal_documentary_links'],2)
        self.assertEqual(out['summary']['cross_sheet_groups'],1)
        self.assertEqual(out['summary']['group_sizes'],[3])
        self.assertEqual(out['summary']['electrical_paths_verified'],0)
        self.assertEqual(out['independent_layout_comparison']['same_layout_feeder'],2)
        for edge in out['reciprocal_links']:
            self.assertEqual(len(edge['evidence']),2)
            self.assertFalse(edge['electrical_path_verified'])

    def test_single_side_not_connected(self):
        d=_base();d['pages'][1]['text_equipment_anchors']=[d['pages'][1]['text_equipment_anchors'][1]]
        out=analyze_cross_sheet(d)
        self.assertEqual(out['summary']['reciprocal_documentary_links'],1)
        self.assertEqual(out['summary']['one_sided_or_ambiguous_links'],1)
        self.assertEqual(out['summary']['group_sizes'],[1,2])

    def test_page_owner_duplicate_same_cu_not_ambiguous(self):
        d=_base();d['source_reconciliation']['conversion_units'][0]['sld_representations'].append(
            {'page':2,'representation_role':'SOURCE_INSTANCE'})
        self.assertEqual(analyze_cross_sheet(d)['summary']['reciprocal_documentary_links'],2)

    def test_multiple_different_cus_same_page_refused(self):
        d=_base();d['source_reconciliation']['conversion_units'][2]['sld_representations'].append(
            {'page':2,'representation_role':'SOURCE_INSTANCE'})
        out=analyze_cross_sheet(d)
        self.assertEqual(out['summary']['reciprocal_documentary_links'],1)
        self.assertEqual(out['summary']['refused_references'],1)
        self.assertEqual(out['refused_references'][0]['reason'],'AMBIGUOUS_OR_MISSING_SOURCE_CU_ON_PAGE')

    def test_noncanonical_target_refused(self):
        d=_base();d['pages'][0]['text_equipment_anchors'][0]['attributes']['instance_hint']='not_here'
        out=analyze_cross_sheet(d)
        self.assertEqual(out['summary']['reciprocal_documentary_links'],1)
        self.assertEqual(out['refused_references'][0]['reason'],'TARGET_NOT_CANONICAL_IN_THIS_PLANT')

    def test_unknown_direction_never_guessed(self):
        d=_base();d['pages'][0]['text_equipment_anchors'][0]['text']='CONNECTED AT CONVERSION UNIT beta'
        out=analyze_cross_sheet(d)
        self.assertEqual(out['summary']['reciprocal_documentary_links'],1)
        self.assertEqual(out['refused_references'][0]['reason'],'UNKNOWN_REFERENCE_DIRECTION')

    def test_duplicate_same_side_is_ambiguous(self):
        d=_base();d['pages'][0]['text_equipment_anchors'].append(
            _ref('R1bis','TO CONVERSION UNIT beta','beta',2))
        out=analyze_cross_sheet(d)
        self.assertEqual(out['summary']['reciprocal_documentary_links'],1)
        self.assertEqual(out['incomplete_links'][0]['status'],'AMBIGUOUS_MULTIPLE_SIDE_REFERENCES')

    def test_layout_disagreement_report_only_not_used_for_grouping(self):
        d=_base();d['source_reconciliation']['cu_mv_membership'][1]['mv_line_instance_key']='FEEDER_Y'
        out=analyze_cross_sheet(d)
        self.assertEqual(out['summary']['reciprocal_documentary_links'],2)
        self.assertEqual(out['summary']['group_sizes'],[3])
        self.assertEqual(out['independent_layout_comparison']['conflicting_layout_feeder'],2)

    def test_reference_not_converted_from_plain_text_or_gt(self):
        d=_base();d['pages'][2]['text_equipment_anchors'][0]['anchor_role']='INSTANCE'
        d['ground_truth']={'expected_feeders':1}
        self.assertEqual(analyze_cross_sheet(d)['summary']['reciprocal_documentary_links'],1)

    def test_multilingual_spanish_italian_portuguese(self):
        d=_base()
        d['pages'][0]['text_equipment_anchors'][0]['text']='A SUBCAMPO beta'
        d['pages'][1]['text_equipment_anchors'][0]['text']='DE SUBCAMPO alpha'
        d['pages'][1]['text_equipment_anchors'][1]['text']='PARA CAMPO gamma'
        d['pages'][2]['text_equipment_anchors'][0]['text']='DA CAMPO beta'
        self.assertEqual(analyze_cross_sheet(d)['summary']['reciprocal_documentary_links'],2)


if __name__=='__main__':unittest.main()
