"""Alpha21 QPS semantic/parentage tests, source evidence separate from operator truth."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from sld_ci_v04_beta3.sap.cad_qps_hierarchy_alpha21 import (
    verified_qps_sequences, validate_operator_review, build_alpha21_hierarchy,
    write_alpha21_outputs,source_sha256,REVIEW_SCHEMA)

P='CI::UNSEEN_PV'

def inputs(groups=(1,2,3),count=5,*,missing=None,ambiguous=False):
    fields=[];graphics=[];pairs=[];converters=[]
    for field_no,g in enumerate(groups,1):
        good=(missing!=g)
        tokens=[{'group_on_drawing':g,'sequence_index':i,'sequence_total':count,
                 'normalized_designator':f'QPS-{g}-{i}/{count}',
                 'ocr_prefix_exact':True} for i in range(1,count+1)]
        boxes=[{'bbox_px':[40*i,100,40*i+40,155]} for i in range(count)]
        fields.append({'field_candidate':field_no,'sequence_complete':good,
                       'qps_documented_count':count if good else None,'ocr_tokens':tokens})
        graphics.append({'page':1,'field_candidate':field_no,
                         'all_graphic_compartments_meet_symbol_test':good,
                         'dc_combiner_like_cabinet_candidates':count})
        if not ambiguous:
            pairs.append({'page':1,'field_candidate':field_no,
                          'converter_candidate_id':f'INV_GRAFICO_{field_no:03d}',
                          'proposed_relation_status':'CORRISPONDENZA_GRAFICA_ORDINALE_NON_VERIFICATA'})
        converters.append({'page':1,'candidate_id':f'INV_GRAFICO_{field_no:03d}'})
    return {'local_ocr_qps_evidence':{'field_sequences':fields},
            'dc_combiner_graphic_evidence':graphics}, {'candidate_graphic_correlations':pairs},converters


def review(pdf, groups=(1,2,3), *,tr=1):
    return {'schema':REVIEW_SCHEMA,'plant_id':P,'source_pdf_sha256':source_sha256(pdf),
            'qps_semantic_class':'STRING_BOX','qps_is_parallel_string_cabinet':True,
            'qps_group_denotes_inverter_number':True,'operator_confirmed':True,
            'operator_evidence':'Documento CAD pagina 1 con verifica manuale CU1 TR1 e QPS numerate',
            'parent_confirmations':[{'qps_group':g,'CU':1,'TR':tr,'INV':g} for g in groups]}

class Alpha21Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.pdf=Path(self.temp.name)/'unseen.pdf';self.pdf.write_bytes(b'%PDF-stub synthetic evidence source')

    def test_eight_or_five_are_source_counts_not_builtin_constants(self):
        for n in (1,4,8,13):
            with self.subTest(n=n):
                a,b,c=inputs(count=n)
                rows=verified_qps_sequences(a,b)
                self.assertEqual([x['qps_documented'] for x in rows],[n]*3)

    def test_no_review_means_no_automatic_sap_owners_or_stringbox_claim(self):
        a,b,c=inputs()
        r,export=build_alpha21_hierarchy(self.pdf,P,a,b,c)
        self.assertIsNone(export)
        self.assertEqual(r['summary']['qps_documented_total'],15)
        self.assertEqual(r['summary']['string_boxes_operator_semantics_resolved'],0)
        self.assertEqual(r['summary']['operator_confirmed_parent_links'],0)
        self.assertEqual(r['summary']['tr_inverter_automatic_electrical_links_verified'],0)

    def test_operator_confirms_one_tr_three_inverters_with_8_qps_each(self):
        a,b,c=inputs(count=8)
        r,e=build_alpha21_hierarchy(self.pdf,P,a,b,c,review(self.pdf))
        self.assertEqual([(x['CU'],x['TR'],x['INV'],x['STR_Box']) for x in e['detail']],
                         [(1,1,1,8),(1,1,2,8),(1,1,3,8)])
        self.assertEqual(e['summary']['tr_inverter_parent_hitl_confirmed'],3)
        self.assertEqual(e['summary']['string_box_quantity_total_resolved'],24)
        self.assertTrue(all('CONTEGGIO_QPS' in x['stato_string_box'] for x in e['evidence']))
        self.assertTrue(all(x['stato_parent']=='CONFERMATO_HITL' for x in e['evidence']))
        self.assertFalse(e['summary']['matrix_flow_import_ready'])
        self.assertEqual(r['summary']['tr_inverter_automatic_electrical_links_verified'],0)

    def test_one_tr_many_inverters_is_not_two_limit(self):
        a,b,c=inputs(groups=(1,2,3,4,5),count=3)
        r,e=build_alpha21_hierarchy(self.pdf,P,a,b,c,review(self.pdf,groups=(1,2,3,4,5)))
        self.assertEqual(len(e['detail']),5)
        self.assertEqual([x['INV'] for x in e['detail']],[1,2,3,4,5])
        self.assertEqual(e['summary']['tr'],1)

    def test_wrong_file_or_plant_review_rejected(self):
        a,b,c=inputs(); rv=review(self.pdf)
        rv['source_pdf_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'PDF differente'):
            build_alpha21_hierarchy(self.pdf,P,a,b,c,rv)
        rv=review(self.pdf);rv['plant_id']='CI::OTHER'
        with self.assertRaisesRegex(ValueError,'impianto differente'):
            build_alpha21_hierarchy(self.pdf,P,a,b,c,rv)

    def test_unconfirmed_and_missing_semantic_mapping_rejected(self):
        a,b,c=inputs();rv=review(self.pdf)
        rv['operator_confirmed']=False
        with self.assertRaises(ValueError):build_alpha21_hierarchy(self.pdf,P,a,b,c,rv)
        rv=review(self.pdf);rv['qps_semantic_class']='COMBINER_OTHER'
        with self.assertRaises(ValueError):build_alpha21_hierarchy(self.pdf,P,a,b,c,rv)

    def test_incomplete_source_blocks_even_full_review(self):
        a,b,c=inputs(missing=2)
        with self.assertRaises(ValueError):build_alpha21_hierarchy(self.pdf,P,a,b,c,review(self.pdf))

    def test_parent_mapping_outside_source_and_wrong_group_rejected(self):
        a,b,c=inputs()
        for malformed in ([(1,1,1,1),(2,1,1,2),(9,1,1,9)],
                          [(1,1,1,2),(2,1,1,2),(3,1,1,3)]):
            rv=review(self.pdf)
            rv['parent_confirmations']=[dict(zip(('qps_group','CU','TR','INV'),v)) for v in malformed]
            with self.assertRaises(ValueError):build_alpha21_hierarchy(self.pdf,P,a,b,c,rv)

    def test_source_group_not_equal_converter_number_abstains_on_bulk_review(self):
        a,b,c=inputs(groups=(2,3,4))
        rv=review(self.pdf,groups=(2,3,4))
        with self.assertRaisesRegex(ValueError,'non allineato'):
            build_alpha21_hierarchy(self.pdf,P,a,b,c,rv)

    def test_duplicate_group_and_unassigned_field_never_claimed(self):
        a,b,c=inputs(groups=(1,1,3))
        self.assertEqual(sum(x['sequence_complete'] for x in verified_qps_sequences(a,b)),2)
        a,b,c=inputs(ambiguous=True)
        self.assertTrue(all(not x['sequence_complete'] for x in verified_qps_sequences(a,b)))

    def test_csv_and_excel_correct_and_safe(self):
        a,b,c=inputs(count=8)
        r,e=build_alpha21_hierarchy(self.pdf,P,a,b,c,review(self.pdf))
        d=Path(self.temp.name)/'out';paths=write_alpha21_outputs(r,e,d)
        self.assertEqual(len((d/'alpha21_CU_TR_INV_STR_Box.csv').read_text(encoding='utf-8-sig').splitlines()),4)
        self.assertIn('1;1;3;8',(d/'alpha21_CU_TR_INV_STR_Box.csv').read_text(encoding='utf-8-sig'))
        with ZipFile(paths['excel']) as z:self.assertIsNone(z.testzip())
        self.assertTrue((d/'alpha21_evidenze.csv').exists())

    def test_unreviewed_only_staging_and_no_hierarchy_excel(self):
        a,b,c=inputs()
        r,e=build_alpha21_hierarchy(self.pdf,P,a,b,c)
        d=Path(self.temp.name)/'out';write_alpha21_outputs(r,e,d)
        self.assertTrue((d/'alpha21_qps_staging.csv').exists())
        self.assertFalse((d/'alpha21_gerarchie_stereotipi.xlsx').exists())

if __name__=='__main__':unittest.main()
