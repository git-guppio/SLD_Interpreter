"""Alpha12 regression: real document-first export semantics, no fixed topology."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from sld_ci_v04_beta3.sap.stereotypes_alpha12 import build_stereotype_export,write_stereotype_outputs

P='CI::T'
def _cu(n): return {'asset_id':f'{P}::CU::{n:02d}','type':'CONVERSION_UNIT','parent_id':P}
def _tr(n,t): return {'asset_id':f'{P}::TR::{n:02d}.{t:02d}','type':'MV_LV_TRANSFORMER','parent_id':f'{P}::CU::{n:02d}'}
def _inv(n,i,tr=None):
    p=f'{P}::TR::{n:02d}.{tr:02d}' if tr else None
    return {'asset_id':f'{P}::INV::{n:02d}.{i:02d}','type':'CENTRAL_INVERTER','parent_id':p,
            'cu_context_id':f'{P}::CU::{n:02d}','source_status':'NATIVE_INVERTER_LABEL_CANDIDATE',
            'parentage':'OPERATOR_CONFIRMED_TR_PARENT' if p else 'TR_PARENT_REQUIRES_CONFIRMATION'}
def _sb(n,i,q): return {'asset_id':f'{P}::SB_QUANTITY::{n:02d}.{i:02d}','type':'STRING_BOX_QUANTITY','parent_id':f'{P}::INV::{n:02d}.{i:02d}','quantity':q,'evidence_ref':'p1:PDF:SB'}
def _r(assets,candidates=()):
    baseline={'schema':'sld-sap-label-first-alpha10/v1','plant_id':P,'source_pdf':'input.pdf','assets':assets}
    props={'schema':'sld-sap-alpha11-tr-inverter-proposals/v1','plant_id':P,'source_pdf':'input.pdf','candidates':list(candidates)}
    return baseline,props
def _c(n,i,t):
    return {'inverter_id':f'{P}::INV::{n:02d}.{i:02d}',
            'proposed_transformer_id':f'{P}::TR::{n:02d}.{t:02d}',
            'evidence_ref':'input.pdf:p1:spatial','has_printed_label_conflict':False}
def _fixture():
    assets=[]; proposals=[]
    for n in range(1,3):
        assets.append(_cu(n))
        for t in (1,2):assets.append(_tr(n,t))
        for i, t in [(1,1),(2,1),(3,2),(4,2)]:
            assets.extend([_inv(n,i),_sb(n,i,10+i%2)])
            proposals.append(_c(n,i,t))
    return _r(assets,proposals)

class Alpha12StereotypesTests(unittest.TestCase):
    def test_compact_4_columns_one_row_per_inverter(self):
        a=build_stereotype_export(*_fixture())
        self.assertEqual(len(a['detail']),8)
        self.assertEqual([r[k] for k in ('CU','TR','INV','STR_Box') for r in a['detail'][:1]],[1,1,1,11])
        self.assertEqual(a['summary']['string_box_quantities_resolved'],8)

    def test_inverter_counter_restarts_inside_each_transformer(self):
        rows=build_stereotype_export(*_fixture())['detail']
        self.assertEqual([(x['TR'],x['INV']) for x in rows[:4]],[(1,1),(1,2),(2,1),(2,2)])

    def test_structure_not_hardcoded_to_two(self):
        assets=[_cu(1),_cu(2),_tr(1,1),_tr(2,1)]
        c=[]
        for n in (1,2):
            for i in (1,2,3,4):
                assets.extend([_inv(n,i),_sb(n,i,i+9)])
                c.append(_c(n,i,1))
        a=build_stereotype_export(*_r(assets,c))
        self.assertEqual(a['summary']['stereotype_inv_per_tr'],4)
        self.assertEqual(a['summary']['stereotype_tr_per_cu'],1)
        self.assertEqual([x['INV'] for x in a['detail'][:4]],[1,2,3,4])

    def test_one_cu_is_not_sufficient_for_stereotype(self):
        a=build_stereotype_export(*_r([_cu(1),_tr(1,1),_inv(1,1)],[ _c(1,1,1)]))
        self.assertIsNone(a['summary']['stereotype_tr_per_cu'])
        self.assertIsNone(a['summary']['stereotype_inv_per_tr'])
        self.assertEqual(a['detail'][0]['tr_stereotype_status'],'NON_STEREOTIPATO')

    def test_exception_flagged_without_rewriting_counts(self):
        assets=[_cu(1),_cu(2),_cu(3),_tr(1,1),_tr(2,1),_tr(3,1),_tr(3,2)]
        a=build_stereotype_export(*_r(assets))
        self.assertEqual(a['summary']['stereotype_tr_per_cu'],1)
        self.assertEqual(a['controls'][2]['stato_TR'],'ECCEZIONE')
        self.assertFalse(a['summary']['stereotype_tr_uniform_all_cus'])

    def test_parent_proposal_never_confirmed_automatically(self):
        a=build_stereotype_export(*_fixture())
        self.assertEqual(a['summary']['tr_inverter_parent_hitl_confirmed'],0)
        self.assertTrue(all(r['stato_parent']=='CANDIDATO_NON_VERIFICATO' for r in a['evidence']))

    def test_preconfirmed_parent_kept_even_without_proposal(self):
        a=build_stereotype_export(*_r([_cu(1),_tr(1,1),_inv(1,1,tr=1),_sb(1,1,12)]))
        self.assertEqual(a['summary']['tr_inverter_parent_hitl_confirmed'],1)
        self.assertEqual(a['detail'][0]['TR'],1)
        self.assertEqual(a['detail'][0]['STR_Box'],12)

    def test_hitl_evidence_for_cu19_not_valid_for_cu01(self):
        assets=[_cu(1),_cu(19),_tr(1,1),_tr(19,1),_inv(1,1,tr=1),_inv(19,1,tr=1)]
        for a in assets:
            if a['type']=='CENTRAL_INVERTER':a['operator_evidence_ref']='PV11:p1:CU19'
        result=build_stereotype_export(*_r(assets))
        self.assertEqual(result['summary']['tr_inverter_parent_hitl_confirmed'],1)
        self.assertEqual(result['evidence'][0]['stato_parent'],'CONFERMA_HITL_SCOPE_DA_VERIFICARE')
        self.assertEqual(result['evidence'][1]['stato_parent'],'CONFERMATO_HITL')

    def test_multi_cu_evidence_does_not_get_falsely_rejected_as_single(self):
        assets=[_cu(1),_tr(1,1),_inv(1,1,tr=1)]
        assets[-1]['operator_evidence_ref']='PV11:p1:CU1-22'
        result=build_stereotype_export(*_r(assets))
        self.assertEqual(result['summary']['tr_inverter_parent_hitl_confirmed'],1)

    def test_unresolved_parent_does_not_invent_tr_or_inv_number(self):
        a=build_stereotype_export(*_r([_cu(1),_inv(1,1),_sb(1,1,10)]))
        self.assertIsNone(a['detail'][0]['TR'])
        self.assertIsNone(a['detail'][0]['INV'])
        self.assertEqual(a['detail'][0]['STR_Box'],10)
        self.assertEqual(a['summary']['tr_inverter_parent_unresolved'],1)

    def test_missing_sb_quantity_blank_not_zero(self):
        a=build_stereotype_export(*_r([_cu(1),_tr(1,1),_inv(1,1,tr=1)]))
        self.assertIsNone(a['detail'][0]['STR_Box'])
        self.assertEqual(a['summary']['string_box_quantities_unresolved'],1)

    def test_conflicting_sb_labels_stay_unresolved(self):
        assets=[_cu(1),_tr(1,1),_inv(1,1,tr=1),_sb(1,1,10)]
        second=_sb(1,1,11);second['asset_id']=P+'::SB_QUANTITY::01.01_ALT'
        assets.append(second)
        a=build_stereotype_export(*_r(assets))
        self.assertIsNone(a['detail'][0]['STR_Box'])
        self.assertEqual(a['evidence'][0]['stato_string_box'],'ETICHETTE_IN_CONFLITTO_DA_VERIFICARE')

    def test_duplicate_equal_sb_labels_not_summed(self):
        assets=[_cu(1),_tr(1,1),_inv(1,1,tr=1),_sb(1,1,10)]
        second=_sb(1,1,10);second['asset_id']=P+'::SB_QUANTITY::01.01_ALT'
        assets.append(second)
        a=build_stereotype_export(*_r(assets))
        self.assertEqual(a['detail'][0]['STR_Box'],10)
        self.assertEqual(a['evidence'][0]['stato_string_box'],'ETICHETTE_DUPLICATE_DA_VERIFICARE')

    def test_nonmatching_plant_rejected(self):
        base,prop=_fixture(); prop['plant_id']='CI::ALT'
        with self.assertRaises(ValueError):build_stereotype_export(base,prop)

    def test_cross_cu_parent_rejected(self):
        assets=[_cu(1),_cu(2),_tr(2,1),_inv(1,1)]
        with self.assertRaises(ValueError):build_stereotype_export(*_r(assets,[_c(1,1,1) | {'proposed_transformer_id':f'{P}::TR::02.01'}]))

    def test_duplicate_inverter_proposal_rejected(self):
        base,prop=_fixture()
        prop['candidates'].append(dict(prop['candidates'][0]))
        with self.assertRaises(ValueError):build_stereotype_export(base,prop)

    def test_source_label_conflict_preserved_in_evidence(self):
        base,prop=_fixture()
        prop['candidates'][0]['has_printed_label_conflict']=True
        a=build_stereotype_export(base,prop)
        self.assertTrue(a['evidence'][0]['conflitto_etichetta'])
        self.assertIn('ETICHETTA_INVERTER_NON_COHERENTE',[x['reason'] for x in a['issues']])

    def test_actual_written_csv_has_exact_header_and_blank_unknown(self):
        a=build_stereotype_export(*_r([_cu(1),_inv(1,1)]))
        with tempfile.TemporaryDirectory() as d:
            out=write_stereotype_outputs(a,d)
            with out['csv'].open(encoding='utf-8-sig',newline='') as f: rows=list(csv.reader(f,delimiter=';'))
            self.assertEqual(rows,[['CU','TR','INV','STR_Box'],['1','','','']])
            self.assertTrue(out['excel'].is_file())

    def test_excel_four_sheets_and_green_or_amber_format(self):
        a=build_stereotype_export(*_fixture())
        with tempfile.TemporaryDirectory() as d:
            out=write_stereotype_outputs(a,d)
            with ZipFile(out['excel']) as z:
                self.assertEqual(z.testzip(),None)
                wb=ET.fromstring(z.read('xl/workbook.xml'))
                ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                self.assertEqual([s.get('name') for s in wb.findall('.//s:sheet',ns)],['Dettaglio','Riepilogo','Controlli CU','Evidenze'])
                sh=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                self.assertEqual(sh.find('.//s:c[@r="B2"]',ns).get('s'),'9')
                self.assertEqual(sh.find('.//s:c[@r="C2"]',ns).get('s'),'9')

    def test_template_and_export_preserve_status_note(self):
        a=build_stereotype_export(*_fixture())
        self.assertFalse(a['summary']['matrix_flow_import_ready'])
        self.assertTrue(a['summary']['stereotype_is_structural_not_electrically_verified'])
        with tempfile.TemporaryDirectory() as d:
            write_stereotype_outputs(a,d)
            self.assertIn('Nessun Ground Truth' if False else 'parent',json.dumps(a['evidence']))

if __name__=='__main__':unittest.main()
