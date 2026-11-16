"""Alpha17 safety tests: graphic repetitions must never be SAP equipment."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from sld_ci_v04_beta3.sap.vector_diagnostics_alpha17 import (
    _group_repeat_shapes, _compare_rasters, vector_only_document,
    inspect_vector_pdf, write_vector_outputs,
)
from sld_ci_v04_beta3.sap_workbench_alpha16 import choose_recognition_mode


class VectorTriageTests(unittest.TestCase):
    def make_pdf(self, path, *, text=False):
        d=fitz.open();p=d.new_page(width=700,height=500)
        for i in range(4):
            x=70+i*125
            sh=p.new_shape()
            sh.draw_rect(fitz.Rect(x,80,x+50,120))
            sh.finish(color=(0,1,1),width=2);sh.commit()
            sh=p.new_shape();sh.draw_rect(fitz.Rect(x+5,200,x+35,230))
            sh.finish(color=(1,0,0),width=2);sh.commit()
        if text:p.insert_text((40,40),'INVERTER PROVA',fontsize=12)
        d.save(str(path));d.close()

    def test_vector_without_text_routes_to_diagnostic(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'geom.pdf';self.make_pdf(p)
            self.assertTrue(vector_only_document(p))
            self.assertEqual(choose_recognition_mode(p),'alpha21-cad')

    def test_vector_with_text_does_not_route_to_diagnostic(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'text.pdf';self.make_pdf(p,text=True)
            self.assertFalse(vector_only_document(p))
            self.assertNotEqual(choose_recognition_mode(p),'alpha21-cad')

    def test_untyped_repetitions_never_invent_assets(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'geom.pdf';self.make_pdf(p)
            res,preview=inspect_vector_pdf(p)
            self.assertEqual(res['result_status'],'DIAGNOSTICA_GEOMETRICA_NON_GERARCHIA_SAP')
            self.assertIsNone(res['verified_inverters'])
            self.assertFalse(res['matrix_flow_import_ready'])
            self.assertGreaterEqual(len(res['geometric_repeat_groups']),1)
            self.assertEqual(res['electrical_connections_verified'],0)
            self.assertTrue(all(g['verified_device_count']==0 for g in res['geometric_repeat_groups']))
            self.assertTrue(preview)

    def test_outputs_create_json_csv_and_png(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'geom.pdf';self.make_pdf(p)
            res,preview=inspect_vector_pdf(p)
            out=write_vector_outputs(res,preview,Path(t)/'out')
            self.assertTrue((out/'alpha17_diagnostica_geometrica.json').is_file())
            self.assertTrue((out/'alpha17_motivi_ripetuti.csv').is_file())
            self.assertTrue((out/'alpha17_anteprima_geometria_p1.png').is_file())
            self.assertIsNone(json.loads((out/'alpha17_diagnostica_geometrica.json').read_text())['verified_CU'])

    def test_self_comparison_equal_and_independence_warning(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'geom.pdf';self.make_pdf(p)
            result=_compare_rasters(p,p)
            self.assertEqual(result['approx_equal_pixel_fraction'],1.0)
            self.assertTrue(result['near_duplicate_candidate'])
            self.assertIn('non prova',result['warning'])

    def test_no_grounds_to_classify_shape_as_inverter(self):
        components=[{'width':50,'height':40,'box':[30,20,80,60],'pixels':400},
                    {'width':51,'height':41,'box':[130,20,181,61],'pixels':400}]
        groups=_group_repeat_shapes(components)
        self.assertEqual(len(groups),1)
        self.assertEqual(len(groups[0]['items']),2)
        self.assertNotIn('asset_type',groups[0])

    def test_empty_vector_document_is_not_positive(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'blank.pdf';d=fitz.open();d.new_page();d.save(p);d.close()
            self.assertFalse(vector_only_document(p))
            self.assertEqual(choose_recognition_mode(p),'alpha12')

if __name__=='__main__':unittest.main()
