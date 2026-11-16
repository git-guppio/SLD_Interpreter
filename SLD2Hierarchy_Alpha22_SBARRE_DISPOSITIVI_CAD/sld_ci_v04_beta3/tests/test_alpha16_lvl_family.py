"""Third-document-family contract tests, no ground-truth input to parser."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf
from sld_ci_v04_beta3.sap.lvl_indexed_alpha16 import (
    detect_lvl_family, extract_lvl_indexed, write_outputs)
from sld_ci_v04_beta3.sap_workbench_alpha16 import choose_recognition_mode


def make_pdf(filename, pages):
    doc=pymupdf.open()
    for records in pages:
        page=doc.new_page(width=1100,height=1100)
        for text,x,y in records:
            page.insert_text((x,y),text,fontsize=11)
    doc.save(str(filename));doc.close()


def item(key,inv,boxes,xx=250):
    return ([(f'Inv.{key}.{inv}',xx,250+inv*55)] +
            [(f'LVL-SB.{key}.{inv}.{serial}-INV.{key}.{inv}',xx+100,450+20*serial) for serial in boxes])


class ThirdFamilyAlpha16(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.pdf=Path(self.t.name)/'random_document.pdf'
    def test_one_transformer_many_inverters_no_fanout_limit(self):
        lines=[('Subcampo 7. (power)',50,40),('800 kVA',250,100),('0,4/20kV',250,118)]
        for inv in range(1,5):lines+=item(7,inv,list(range(1,inv+1)))
        make_pdf(self.pdf,[lines])
        r=extract_lvl_indexed(self.pdf,'generic_7')
        self.assertEqual((r['summary']['cu'],r['summary']['tr_candidate'],r['summary']['inverters']),(1,1,4))
        self.assertEqual([x['STR_Box'] for x in r['rows']],[1,2,3,4])
        self.assertEqual([x['INV'] for x in r['rows']],[1,2,3,4])
        self.assertEqual({x['TR'] for x in r['rows']},{1})
        self.assertEqual(r['summary']['parent_confirmed'],0)
        self.assertTrue(detect_lvl_family(self.pdf))
    def test_serial_gap_not_counted_as_quantity(self):
        make_pdf(self.pdf,[[('500 kVA',250,100),('0,4/30KV',250,120)]+item(7,1,[1,3])])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertIsNone(r['rows'][0]['STR_Box'])
        self.assertEqual(r['rows'][0]['box_missing_ids'],[2])
        self.assertEqual(r['rows'][0]['box_max_id'],3)
    def test_explicit_box_scope_conflict_is_not_assigned(self):
        make_pdf(self.pdf,[[('Inv.7.1',250,200),('LVL-SB.7.1.1-INV.7.2',400,300)]])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertIsNone(r['rows'][0]['STR_Box'])
        self.assertTrue(any(x['code']=='BOX_INVERTER_TAG_CONFLICT' for x in r['issues']))
    def test_rating_without_voltage_does_not_create_transformer(self):
        make_pdf(self.pdf,[[('900 kVA',200,100)]+item(2,1,[1])])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertEqual(r['summary']['tr_candidate'],0)
        self.assertIsNone(r['rows'][0]['TR'])
        self.assertEqual(r['rows'][0]['STR_Box'],1)
    def test_multi_CU_page_does_not_guess_transformer_ownership(self):
        records=[('900 kVA',250,100),('0,4/30kV',250,120)]+item(1,1,[1],200)+item(2,1,[1],600)
        make_pdf(self.pdf,[records])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertEqual(r['summary']['inverters'],2)
        self.assertEqual(r['summary']['tr_candidate'],0)
        self.assertTrue(all(x['TR'] is None for x in r['rows']))
    def test_ambiguous_transformer_nearness_unresolved(self):
        lines=[('900 kVA',150,100),('0,4/30kV',150,120),
               ('850 kVA',350,100),('0,4/30kV',350,120)]+item(1,1,[1],250)
        make_pdf(self.pdf,[lines])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertIsNone(r['rows'][0]['TR'])
        self.assertEqual(r['rows'][0]['parent_status'],'GEOMETRIA_AMBIGUA')
    def test_standalone_inv_required_not_cable_label(self):
        make_pdf(self.pdf,[[('LVL-SB.3.1.1-INV.3.1',300,300),('20 STRING',300,450)]])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertEqual(r['summary']['inverters'],0)
        self.assertFalse(detect_lvl_family(self.pdf))
        self.assertEqual(choose_recognition_mode(self.pdf),'alpha12')
    def test_two_transformers_are_locally_numbered_and_rows_sorted(self):
        lines=[('900 kVA',200,100),('0,4/30kV',200,120),
               ('850 kVA',800,100),('0,4/30kV',800,120)]
        lines+=item(2,1,[1,2],850)+item(2,2,[1,2,3],250)+item(2,3,[1],250)
        make_pdf(self.pdf,[lines])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertEqual([(x['TR'],x['INV'],x['STR_Box']) for x in r['rows']],[(1,1,3),(1,2,1),(2,1,2)])
        self.assertEqual(r['summary']['tr_candidate'],2)
        self.assertEqual(r['summary']['parent_confirmed'],0)
    def test_outputs_four_columns_evidence_and_zip_spreadsheet(self):
        make_pdf(self.pdf,[[('900 kVA',250,100),('0,4/30kV',250,120)]+item(1,1,[1,2])])
        original=self.pdf.read_bytes()
        result=extract_lvl_indexed(self.pdf,'AB')
        out=write_outputs(result,Path(self.t.name)/'reports')
        with (out/'alpha16_CU_TR_INV_STR_Box.csv').open(encoding='utf-8-sig') as handle:
            rows=list(csv.DictReader(handle,delimiter=';'))
        self.assertEqual(rows,[{'CU':'1','TR':'1','INV':'1','STR_Box':'2'}])
        self.assertIn('CANDIDATO_PER_PROSSIMITA_X', (out/'alpha16_evidenze.csv').read_text(encoding='utf-8-sig'))
        self.assertEqual(self.pdf.read_bytes(),original)
        with ZipFile(out/'alpha16_gerarchie_stereotipi.xlsx') as z:
            self.assertIsNone(z.testzip())
            self.assertIn('xl/workbook.xml',z.namelist())
    def test_plant_scope_and_page_provenance(self):
        make_pdf(self.pdf,[[('800 kVA',250,100),('0,4/20kV',250,120)]+item(11,1,[1])])
        result=extract_lvl_indexed(self.pdf,'FOREIGN_01')
        self.assertEqual(result['plant_id'],'CI::FOREIGN_01')
        self.assertIn(':p1:',result['rows'][0]['inverter_evidence'])
        self.assertIn('LVL-SB.',result['rows'][0]['box_evidence'])
        with self.assertRaises(ValueError):extract_lvl_indexed(self.pdf,'../../outside')
    def test_no_text_no_fabrication(self):
        make_pdf(self.pdf,[[('unrelated drawing',50,60)]])
        r=extract_lvl_indexed(self.pdf,'AB')
        self.assertEqual(r['summary']['cu'],0)
        self.assertEqual(r['summary']['inverters'],0)
        self.assertEqual(r['summary']['tr_candidate'],0)

if __name__=='__main__':unittest.main()
