"""Alpha18 candidate semantics: never confuse structural evidence with SAP asset."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from sld_ci_v04_beta3.sap.vector_semantics_alpha18 import (
    inspect_vector_semantics, write_semantics_outputs, group_downstream_panels)
from sld_ci_v04_beta3.sap_workbench_alpha16 import choose_recognition_mode

CYAN=(0, 1, 1)
RED=(1, 0, 0)
BLACK=(0, 0, 0)


def make_vector_cad(path, *, converter=True, bus=True, texts=False, count=3):
    doc=fitz.open()
    page=doc.new_page(width=900,height=630)
    for n in range(count):
        x=120+n*230
        y=160
        page.draw_rect(fitz.Rect(x,y,x+56,y+65),color=CYAN,width=1.3)
        if converter:
            page.draw_rect(fitz.Rect(x+8,y+7,x+25,y+24),color=BLACK,width=1)
            page.draw_line((x+9,y+22),(x+23,y+8),color=BLACK,width=1.3)
            page.draw_line((x+9,y+19),(x+20,y+8),color=BLACK,width=1.0)
        if bus:
            page.draw_line((x+5,y+50),(x+51,y+50),color=RED,width=1.1)
            for j in range(8):
                xx=x+6+6*j
                page.draw_line((xx,y+50),(xx,y+65),color=RED,width=1.1)
                page.draw_line((xx,y+70),(xx,y+85),color=RED,width=1.1)
        # geometric panels downstream without a named string-box label
        for yy in (325,455):
            for k in range(4):
                xx=x-75+k*36
                page.draw_rect(fitz.Rect(xx,yy,xx+32,yy+25),color=CYAN,width=1.2)
    if texts:
        page.insert_text((30,30),'TESTO DOCUMENTALE',fontsize=10)
    doc.save(str(path));doc.close()


class Alpha18VectorSemanticTests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.pdf=Path(self.d.name)/'unknown_document.pdf'

    def test_structural_converter_requiring_three_independent_clues(self):
        make_vector_cad(self.pdf)
        res, previews=inspect_vector_semantics(self.pdf)
        self.assertEqual(res['schema'],'sld-alpha18-cad-candidates/v1')
        self.assertEqual(len(res['converter_candidates']),3)
        self.assertEqual([x['outgoing_branches_observed'] for x in res['converter_candidates']],[8,8,8])
        self.assertTrue(previews)

    def test_converter_glyph_alone_is_insufficient(self):
        make_vector_cad(self.pdf,bus=False)
        res,_=inspect_vector_semantics(self.pdf)
        self.assertEqual(res['converter_candidates'],[])

    def test_red_comb_without_converter_glyph_is_insufficient(self):
        make_vector_cad(self.pdf,converter=False)
        res,_=inspect_vector_semantics(self.pdf)
        self.assertEqual(res['converter_candidates'],[])

    def test_no_non_native_routing_if_text_exists(self):
        make_vector_cad(self.pdf,texts=True)
        res,_=inspect_vector_semantics(self.pdf)
        self.assertEqual(res['converter_candidates'],[])
        self.assertNotEqual(choose_recognition_mode(self.pdf),'alpha21-cad')

    def test_downstream_panels_no_parent_claim(self):
        panels=[{'bbox_px':[10,100,170,130],'contained_cyan_compartments':4,'page':1},
                {'bbox_px':[25,190,185,220],'contained_cyan_compartments':4,'page':1},
                {'bbox_px':[330,100,490,130],'contained_cyan_compartments':3,'page':1},
                {'bbox_px':[345,190,505,220],'contained_cyan_compartments':5,'page':1}]
        groups=group_downstream_panels(panels)
        self.assertEqual([x['compartments_observed'] for x in groups],[8,8])
        self.assertTrue(all('SENZA_PARENT' in g['status'] for g in groups))

    def test_no_sap_owners_no_box_count_and_no_txt(self):
        make_vector_cad(self.pdf)
        source=self.pdf.read_bytes()
        res,preview=inspect_vector_semantics(self.pdf)
        self.assertIsNone(res['verified_CU'])
        self.assertIsNone(res['verified_TR'])
        self.assertIsNone(res['verified_inverters'])
        self.assertIsNone(res['verified_string_boxes'])
        self.assertEqual(res['verified_tr_inverter_parent_links'],0)
        self.assertFalse(res['matrix_flow_import_ready'])
        self.assertFalse(res['ground_truth_used'])
        self.assertEqual(self.pdf.read_bytes(),source)
        out=write_semantics_outputs(res,preview,Path(self.d.name)/'out')
        self.assertTrue((out/'alpha18_anteprima_simboli_p1.png').is_file())
        self.assertTrue((out/'alpha18_candidati_vettoriali.json').is_file())
        self.assertFalse((out/'alpha18_CU_TR_INV_STR_Box.csv').exists())
        with (out/'alpha18_candidati_inverter.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(len(list(csv.DictReader(f,delimiter=';'))),3)
        self.assertEqual(json.loads((out/'alpha18_candidati_vettoriali.json').read_text())['verified_inverters'],None)

    def test_empty_drawing_does_not_create_cad_cabinets(self):
        doc=fitz.open();doc.new_page();doc.save(self.pdf);doc.close()
        res,_=inspect_vector_semantics(self.pdf)
        self.assertEqual(res['converter_candidates'],[])

if __name__=='__main__':unittest.main()
