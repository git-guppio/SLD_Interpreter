import csv
import tempfile
import unittest
from pathlib import Path
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

from sld_ci_v04_beta3.sap.multistyle_alpha15 import extract_indexed_families,write_csv_outputs
from sld_ci_v04_beta3.sap_workbench_alpha15 import choose_recognition_mode


def fake_pdf(path,pages):
    doc=pymupdf.open()
    for strings in pages:
        page=doc.new_page(width=800,height=800)
        for i,s in enumerate(strings):
            page.insert_text((30,40+i*24),s,fontsize=10)
    doc.save(str(path));doc.close()


class MultistyleAlpha15(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf=Path(self.tmp.name)/'non_specifico.pdf'
    def test_generic_plant_prefix_changes_without_special_case(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01'],['CENTRO DE TRANSFORMACION CT-01',
            'INVERSOR FOO-INV-01-01','FOO-CST-01-I01-12-01','FOO-CST-01-I01-20-02']])
        r=extract_indexed_families(self.pdf,'CHECK')
        self.assertEqual((r['summary']['cu'],r['summary']['tr_candidate'],r['summary']['inverters']),(1,1,1))
        self.assertEqual(r['rows'][0]['STR_Box'],2)
        self.assertEqual(r['rows'][0]['TR'],1)
        self.assertEqual(r['rows'][0]['INV'],1)
        self.assertEqual(r['summary']['parent_confirmed'],0)
    def test_strings_are_not_string_boxes(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01','FOO-INV-01-01','20 STRINGS']])
        r=extract_indexed_families(self.pdf,'CHECK')
        self.assertIsNone(r['rows'][0]['STR_Box'])
    def test_serial_gap_is_unresolved_not_max_claim(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01','FOO-INV-01-01','FOO-CST-01-I01-20-01',
                            'FOO-CST-01-I01-20-03']])
        r=extract_indexed_families(self.pdf,'CHECK')
        self.assertIsNone(r['rows'][0]['STR_Box'])
        self.assertEqual(r['rows'][0]['box_max_id'],3)
        self.assertEqual(r['rows'][0]['box_missing_ids'],[2])
        self.assertTrue(any(x['code']=='BOX_SERIAL_GAP' for x in r['issues']))
    def test_no_fixed_transf_inverter_cardinality(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01','FOO-INV-01-01', 'FOO-INV-01-02','FOO-INV-01-03']])
        r=extract_indexed_families(self.pdf,'CHECK')
        self.assertEqual(r['summary']['inverters'],3)
        self.assertEqual(r['summary']['parent_candidates'],1)
        self.assertEqual(r['summary']['parent_confirmed'],0)
    def test_other_plant_box_prefix_never_assigned(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01','FOO-INV-01-01','BAR-CST-01-I01-20-01']])
        r=extract_indexed_families(self.pdf,'CHECK')
        self.assertIsNone(r['rows'][0]['STR_Box'])
    def test_cross_page_box_reference_rejected(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01','FOO-CST-01-I01-20-01'],
                           ['FOO-INV-01-01','FOO-CST-01-I01-20-02']])
        r=extract_indexed_families(self.pdf,'CHECK')
        self.assertIsNone(r['rows'][0]['STR_Box'])
        self.assertEqual(r['rows'][0]['box_missing_ids'],[1])
    def test_pdf_with_no_native_labels_does_not_invent_assets(self):
        fake_pdf(self.pdf,[['hello world, 20 STRINGS']])
        r=extract_indexed_families(self.pdf,'CHECK')
        self.assertEqual(r['summary']['inverters'],0)
        self.assertEqual(choose_recognition_mode(self.pdf),'alpha12')
    def test_output_rows_and_valid_excel(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01','FOO-INV-01-01','FOO-CST-01-I01-20-01']])
        r=extract_indexed_families(self.pdf,'CHECK')
        output=Path(self.tmp.name)/'out'
        write_csv_outputs(r,output)
        self.assertTrue((output/'alpha15_gerarchie_stereotipi.xlsx').is_file())
        with (output/'alpha15_CU_TR_INV_STR_Box.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f,delimiter=';'))
        self.assertEqual(rows,[{'CU':'1','TR':'1','INV':'1','STR_Box':'1'}])
        self.assertEqual(choose_recognition_mode(self.pdf),'alpha15-indexed')
    def test_invalid_plant_id_rejected(self):
        fake_pdf(self.pdf,[['FOO-TPO-01-01','FOO-INV-01-01']])
        with self.assertRaises(ValueError):extract_indexed_families(self.pdf,'../other')

if __name__=='__main__':unittest.main()
