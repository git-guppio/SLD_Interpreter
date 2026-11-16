"""Alpha10: safe SAP positional labels, HITL scoping, no GT injection."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

import pymupdf
from sld_ci_v04_beta3.sap.label_first import (extract_candidates,_assign_box,_nearest_cu,
    REVIEW_SCHEMA)


class Alpha10SapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pdf=Path(self.temp.name)/'local.pdf'

    def make_pdf(self,content=True,repeat=False):
        d=pymupdf.open();p=d.new_page(width=650,height=500)
        if content:
            p.insert_text((350,100),'C 1')
            p.insert_text((345,175),'TRANSFORMER 1.700 kVA')
            p.insert_text((308,280),'I 1.1')
            p.insert_text((339.43,385),'10 STRING BOX')
            if repeat:p.insert_text((350,125),'C 1')
        d.save(self.pdf);d.close()

    def test_native_explicit_labels_and_spatial_chain(self):
        self.make_pdf()
        r=extract_candidates(self.pdf,'TEST')
        s=r['summary']
        self.assertEqual([s[k] for k in ('cu_labels','transformer_label_candidates','inverter_label_candidates',
                                        'string_box_quantity_labels_matched','string_boxes_documentary_quantity_matched')],
                         [1,1,1,1,10])
        self.assertEqual(s['unconfirmed_inverter_transformer_parents'],1)
        self.assertTrue(all('evidence_ref' in a for a in r['assets']))
        self.assertFalse(r['matrix_flow_import_ready'])

    def test_no_text_remains_unresolved(self):
        self.make_pdf(False)
        r=extract_candidates(self.pdf,'T')
        self.assertEqual(r['summary']['cu_labels'],0)
        self.assertEqual(r['summary']['string_boxes_documentary_quantity_matched'],0)
        self.assertEqual(r['status'],'NEEDS_GEOMETRY_OCR_OR_HITL')
        self.assertTrue(any(a['reason']=='NO_CU_NATIVE_LABELS_OCR_OR_HITL_REQUIRED' for a in r['issues']))

    def test_duplicate_cu_rejected_from_asset_count(self):
        self.make_pdf(True,repeat=True)
        r=extract_candidates(self.pdf,'T')
        self.assertEqual(r['summary']['cu_labels'],1)
        self.assertTrue(any(a['reason']=='REPEATED_CU_TAG' for a in r['issues']))

    def test_inverter_tag_prefix_conflict_preserved(self):
        cus=[{'number':19,'xy':(350,100)}]
        self.assertEqual(_nearest_cu(cus,(308,280))['number'],19)

    def test_distant_unmatched_cu(self):
        self.assertIsNone(_nearest_cu([{'xy':(350,100)}],(2000,2000)))

    def test_ambiguous_stringbox_never_forced(self):
        inv=[{'page':1,'xy':(300,100),'tag':'I 1.1'},
             {'page':1,'xy':(300.5,100),'tag':'I 1.2'}]
        self.assertIsNone(_assign_box(inv,{'page':1,'xy':(331,207)}))

    def test_plant_scope_review_rejected(self):
        self.make_pdf()
        r={'schema':REVIEW_SCHEMA,'plant_id':'CI::DIFFERENT',
           'confirmed_tr_inverter_groups':[]}
        with self.assertRaises(ValueError):extract_candidates(self.pdf,'TEST',r)

    def test_scoped_group_confirms_only_selected_inverter(self):
        self.make_pdf()
        r={'schema':REVIEW_SCHEMA,'plant_id':'CI::TEST','confirmed_tr_inverter_groups':[
           {'cu_ids':[1],'transformer_slot':1,'inverter_slots':[1],
            'evidence_ref':'operator:diagram:p1:TR1->INV1'}]}
        z=extract_candidates(self.pdf,'TEST',r)
        self.assertEqual(z['summary']['unconfirmed_inverter_transformer_parents'],0)
        inv=next(a for a in z['assets'] if a['type']=='CENTRAL_INVERTER')
        self.assertEqual(inv['parent_id'],'CI::TEST::TR::01.01')
        self.assertEqual(inv['parentage'],'OPERATOR_CONFIRMED_TR_PARENT')

    def test_review_missing_transformer_rejected(self):
        self.make_pdf()
        r={'schema':REVIEW_SCHEMA,'plant_id':'CI::TEST','confirmed_tr_inverter_groups':[
           {'cu_ids':[1],'transformer_slot':2,'inverter_slots':[1],
            'evidence_ref':'operator:diagram'}]}
        with self.assertRaises(ValueError):extract_candidates(self.pdf,'TEST',r)

    def test_no_implicit_child_for_blank_document(self):
        self.make_pdf(False)
        z=extract_candidates(self.pdf,'T')
        self.assertEqual(z['assets'],[])

    def test_operator_confirmed_on_textless_with_evidence(self):
        self.make_pdf(False)
        cu='CI::T::CU::01'; inv='CI::T::INV::01.01'
        r={'schema':REVIEW_SCHEMA,'plant_id':'CI::T','confirmed_assets':[
            {'asset_id':cu,'type':'CONVERSION_UNIT','parent_id':'CI::T','evidence_ref':'SLD:p1:CU'},
            {'asset_id':inv,'type':'CENTRAL_INVERTER','parent_id':None,
             'cu_context_id':cu,'evidence_ref':'SLD:p1:INV1'},
            {'asset_id':'CI::T::SB_QUANTITY::01.01','type':'STRING_BOX_QUANTITY',
             'parent_id':inv,'quantity':16,'evidence_ref':'SLD:p1:SB16'},
        ]}
        z=extract_candidates(self.pdf,'T',r)
        self.assertEqual(z['summary']['cu_labels'],1)
        self.assertEqual(z['summary']['inverter_label_candidates'],1)
        self.assertEqual(z['summary']['string_boxes_documentary_quantity_matched'],16)
        self.assertEqual(z['summary']['unconfirmed_inverter_transformer_parents'],1)
        self.assertTrue(all(a['source_status']=='OPERATOR_CONFIRMED' for a in z['assets']))

    def test_operator_requires_actual_evidence(self):
        self.make_pdf(False)
        with self.assertRaises(ValueError):
            extract_candidates(self.pdf,'T',{'schema':REVIEW_SCHEMA,'plant_id':'CI::T',
                'confirmed_assets':[{'asset_id':'CI::T::CU::01','type':'CONVERSION_UNIT',
                                     'parent_id':'CI::T','evidence_ref':''}]})

    def test_illegal_parent_child_rejected(self):
        self.make_pdf(False)
        with self.assertRaises(ValueError):
            extract_candidates(self.pdf,'T',{'schema':REVIEW_SCHEMA,'plant_id':'CI::T',
                'confirmed_assets':[{'asset_id':'CI::T::INV::01','type':'CENTRAL_INVERTER',
                                     'parent_id':'CI::T','evidence_ref':'p1'}]})

    def test_quantity_cannot_invent_multiple_inverters(self):
        self.make_pdf(False)
        with self.assertRaises(ValueError):
            extract_candidates(self.pdf,'T',{'schema':REVIEW_SCHEMA,'plant_id':'CI::T',
                'confirmed_assets':[{'asset_id':'CI::T::CU::01','type':'CONVERSION_UNIT',
                                     'quantity':3,'parent_id':'CI::T','evidence_ref':'p1'}]})

    def test_operator_cannot_duplicate_source_asset(self):
        self.make_pdf()
        with self.assertRaises(ValueError):
            extract_candidates(self.pdf,'TEST',{'schema':REVIEW_SCHEMA,'plant_id':'CI::TEST',
                'confirmed_assets':[{'asset_id':'CI::TEST::CU::01','type':'CONVERSION_UNIT',
                                     'parent_id':'CI::TEST','evidence_ref':'p1'}]})

    def test_no_gt_file_argument_or_hidden_seed(self):
        self.make_pdf()
        a=extract_candidates(self.pdf,'TEST')
        self.assertFalse(a.get('ground_truth_used_to_modify_inference',False))
        self.assertTrue(a['provenance_policy'].startswith('Native text'))


    def test_many_inverters_one_transformer_operator_confirmed(self):
        d=pymupdf.open();p=d.new_page(width=650,height=500)
        p.insert_text((350,100),'C 1')
        p.insert_text((345,175),'TRANSFORMER 1.700 kVA')
        for slot,x in enumerate((308,256,204),1):
            p.insert_text((x,280),f'I 1.{slot}')
            p.insert_text((x+31.43,385),'10 STRING BOX')
        d.save(self.pdf);d.close()
        r={'schema':REVIEW_SCHEMA,'plant_id':'CI::T','confirmed_tr_inverter_groups':[
           {'cu_ids':[1],'transformer_slot':1,'inverter_slots':[1,2,3],
            'evidence_ref':'verified:SLD:p1:one TR with 3 INV'}]}
        result=extract_candidates(self.pdf,'T',r)
        self.assertEqual(result['summary']['inverter_label_candidates'],3)
        self.assertEqual(result['summary']['unconfirmed_inverter_transformer_parents'],0)
        self.assertEqual({a['parent_id'] for a in result['assets'] if a['type']=='CENTRAL_INVERTER'},
                         {'CI::T::TR::01.01'})

    def test_separate_gt_comparison_does_not_change_extracted_rows(self):
        from sld_ci_v04_beta3.sap.reference_validation import compare_pampa_format
        import json
        report=Path(self.temp.name)/'report.json'
        reference=Path(self.temp.name)/'reference.txt'
        output=Path(self.temp.name)/'result.csv'
        report.write_text(json.dumps({'assets':[{'type':'STRING_BOX_QUANTITY',
            'parent_id':'CI::T::INV::01.01','quantity':10,'evidence_ref':'pdf:p1:xy'}]}),encoding='utf-8')
        reference.write_text('CU1 - TR1 - INV1 - SB11',encoding='utf-8')
        result=compare_pampa_format(report,reference,output)
        self.assertEqual(result['per_inverter_matching'],0)
        self.assertEqual(result['mismatches'],[(1,1,11,10)])
        self.assertEqual(json.loads(report.read_text())['assets'][0]['quantity'],10)

if __name__=='__main__':unittest.main()
