"""Alpha13 automated headless checks: PDF crop, scoped operator HITL, audit."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from sld_ci_v04_beta3.sap.evidence_visual_alpha13 import (
    HITL_SCHEMA, VisualReviewLedger, crop_plan, evidence_is_complete,
    load_evidence, markers_for_record, parse_evidence_ref, render_preview,
)

P='CI::PV11_TEST'


def evidence_row(cu:int,slot:int,tr:int=1,quantity:int=10):
    name='input.pdf'
    return {'CU':cu,'TR':tr,'INV':slot,'STR_Box':quantity,
      'asset_id_originale':f'{P}::INV::{cu:02d}.{slot:02d}',
      'slot_INV_originale':slot,'stato_parent':'CANDIDATO_NON_VERIFICATO',
      'stato_string_box':'QUANTITA_DA_ETICHETTA',
      'conflitto_etichetta':False,
      'evidenza_parent':f'{name}:p1:I {cu}.{slot}:xy=(125.0, 200.0) | '
                         f'{name}:p1:TRANSFORMER 1.700 kVA:xy=(200.0, 140.0)',
      'evidenza_string_box':f'{name}:p1:{quantity} STRING BOX:xy=(270.0, 240.0)'}


def make_fixture(folder:Path):
    pdf=folder/'input.pdf'
    doc=fitz.open();page=doc.new_page(width=600,height=500)
    for x,y,txt in [(125,200,'I 1.1'),(200,140,'TR'),(270,240,'10 STRING BOX')]:
        page.insert_text((x,y),txt,fontsize=14)
    page.draw_line((220,145),(130,195),color=(0,0,0))
    doc.save(pdf);doc.close()
    report=folder/'alpha12_riepilogo.json'
    report.write_text(json.dumps({'schema':'sld-sap-stereotypes-alpha12/v1',
        'plant_id':P,'source_pdf':str(pdf),'evidence':[evidence_row(1,1)]}),encoding='utf-8')
    return pdf,report


class Alpha13EvidenceTests(unittest.TestCase):
    def test_evidence_parsing_original_native_xy(self):
        p=parse_evidence_ref(evidence_row(1,1)['evidenza_parent'])
        self.assertEqual(len(p),2)
        self.assertEqual(p[0]['label'],'I 1.1')
        self.assertEqual(p[1]['page'],1)
        self.assertEqual(p[1]['x'],200.0)

    def test_non_coordinate_is_not_invented(self):
        self.assertEqual(parse_evidence_ref('PDF:p1:TRANSFORMER: no xy'),[])
        self.assertEqual(parse_evidence_ref(''),[])

    def test_records_do_not_leak_other_plants(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            doc=json.loads(report.read_text());doc['evidence'][0]['asset_id_originale']='CI::OTHER::INV::01.01'
            report.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):load_evidence(report,pdf)

    def test_wrong_source_pdf_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            other=f/'other.pdf';other.write_bytes(pdf.read_bytes())
            with self.assertRaises(ValueError):load_evidence(report,other)

    def test_one_row_scope_confirmed_not_bulk(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            data=json.loads(report.read_text())
            other=evidence_row(2,1)
            data['evidence'].append(other)
            report.write_text(json.dumps(data))
            ledger=VisualReviewLedger(report,pdf,f/'output')
            ledger.set_decision(data['evidence'][0]['asset_id_originale'],'CONFERMATO_VISIVO')
            review=json.loads(ledger.out_json.read_text())
            self.assertEqual(review['schema'],HITL_SCHEMA)
            self.assertEqual(review['confirmed_tr_inverter_groups'],[{
              'cu_ids':[1],'transformer_slot':1,'inverter_slots':[1],
              'evidence_ref':'ALPHA13_VISUAL:input.pdf:p1:CU1:TR1:I1'}])
            self.assertEqual(len(review['alpha13_visual_checks']),1)

    def test_inverter_number_uses_original_slot(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            data=json.loads(report.read_text());data['evidence']=[evidence_row(1,3,tr=2)]
            data['evidence'][0]['INV']=1  # Local INV index restarts under TR2
            report.write_text(json.dumps(data))
            ledger=VisualReviewLedger(report,pdf,f/'review')
            ledger.set_decision(data['evidence'][0]['asset_id_originale'],'CONFERMATO_VISIVO')
            self.assertEqual(ledger.make_hitl()['confirmed_tr_inverter_groups'][0]['inverter_slots'],[3])

    def test_error_is_audit_only(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            ledger=VisualReviewLedger(report,pdf,f/'review')
            asset=ledger.records[0]['asset_id_originale']
            ledger.set_decision(asset,'DA_CORREGGERE','Il parent corretto e TR2; verificare disegno')
            self.assertEqual(ledger.make_hitl()['confirmed_tr_inverter_groups'],[])
            self.assertEqual(ledger.make_hitl()['alpha13_visual_checks'][0]['notes'],
                             'Il parent corretto e TR2; verificare disegno')
            with self.assertRaises(ValueError):ledger.set_decision(asset,'DA_CORREGGERE','  ')

    def test_unresolved_quantity_cannot_be_confirmed(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            data=json.loads(report.read_text());data['evidence'][0]['STR_Box']=None
            data['evidence'][0]['stato_string_box']='QUANTITA_NON_RISOLTA'
            report.write_text(json.dumps(data))
            ledger=VisualReviewLedger(report,pdf,f/'review')
            with self.assertRaises(ValueError):ledger.set_decision(ledger.records[0]['asset_id_originale'],'CONFERMATO_VISIVO')
            self.assertFalse(ledger.out_json.exists())

    def test_invalid_parent_scope_cannot_be_confirmed(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            data=json.loads(report.read_text());data['evidence'][0]['stato_parent']='CONFERMA_HITL_SCOPE_DA_VERIFICARE'
            report.write_text(json.dumps(data))
            ledger=VisualReviewLedger(report,pdf,f/'review')
            self.assertFalse(evidence_is_complete(ledger.records[0],pdf.name))

    def test_resume_same_pdf_report_and_refuse_changed_report(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            ledger=VisualReviewLedger(report,pdf,f/'review')
            asset=ledger.records[0]['asset_id_originale']
            ledger.set_decision(asset,'CONFERMATO_VISIVO')
            again=VisualReviewLedger(report,pdf,f/'review')
            self.assertEqual(again.decisions[asset]['status'],'CONFERMATO_VISIVO')
            data=json.loads(report.read_text());data['evidence'][0]['STR_Box']=11
            report.write_text(json.dumps(data))
            with self.assertRaises(ValueError):VisualReviewLedger(report,pdf,f/'review')

    def test_pdf_crop_renders_png_and_all_markers(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            _,records=load_evidence(report,pdf)
            with fitz.open(pdf) as doc:
                png,markers,geometry=render_preview(doc[0],records[0],pdf.name)
                self.assertTrue(png.startswith(b'\x89PNG'))
                self.assertEqual({m['kind'] for m in markers},{'TR','INV','STR_Box'})
                self.assertTrue(all(0<=m['px']<=geometry['width'] for m in markers))
                self.assertTrue(all(0<=m['py']<=geometry['height'] for m in markers))

    def test_rotation_coordinates_to_page_display_space(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            with fitz.open(pdf) as doc:
                doc[0].set_rotation(270)
                rotated=f/'rotated.pdf';doc.save(rotated)
            with fitz.open(rotated) as doc:
                row=evidence_row(1,1)
                clip,marks=crop_plan(doc[0],row,pdf.name)
                # Unrotated (125,200) maps to (200, 600-125)
                inverter=next(m for m in marks if m['kind']=='INV')
                self.assertAlmostEqual(inverter['vx'],200,delta=0.1)
                self.assertAlmostEqual(inverter['vy'],475,delta=0.1)
                self.assertTrue(clip.contains(fitz.Point(inverter['vx'],inverter['vy'])))

    def test_source_files_unchanged_during_verification(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d);pdf,report=make_fixture(f)
            before=(pdf.read_bytes(),report.read_bytes())
            ledger=VisualReviewLedger(report,pdf,f/'review')
            ledger.set_decision(ledger.records[0]['asset_id_originale'],'CONFERMATO_VISIVO')
            self.assertEqual((pdf.read_bytes(),report.read_bytes()),before)
            ledger.clear_decision(ledger.records[0]['asset_id_originale'])
            self.assertEqual(ledger.make_hitl()['confirmed_tr_inverter_groups'],[])


if __name__ == '__main__':
    unittest.main()
