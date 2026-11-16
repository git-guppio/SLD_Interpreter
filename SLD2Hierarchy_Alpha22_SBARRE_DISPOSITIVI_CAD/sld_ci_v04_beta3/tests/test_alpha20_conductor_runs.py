"""Alpha20 tests: no cross-gap fabrication; source-grounded CAD strokes."""
import hashlib
import tempfile
import unittest
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from sld_ci_v04_beta3.sap.cad_conductor_graph_alpha20 import (
    conductor_components,trace_converter_inputs,extract_solid_conductors,
    inspect_cad_conductor_runs,write_cad_conductor_outputs)


def c(i,x,y=100):
    return {'page':1,'candidate_id':f'I{i}', 'bbox_px':[x-25,y,x+25,y+60]}


class Alpha20Tests(unittest.TestCase):
    def test_three_independent_leads_to_aligned_terminals(self):
        s=[((100,100),(100,80)),((100,80),(144,80)),((144,80),(144,60)),
           ((220,100),(220,60)),
           ((340,100),(340,80)),((340,80),(296,80)),((296,80),(296,60))]
        rows=trace_converter_inputs([c(1,100),c(2,220),c(3,340)],s)
        self.assertEqual([x['segments_in_run'] for x in rows],[3,1,3])
        self.assertEqual([x['upstream_terminal_px'] for x in rows],[[144,60],[220,60],[296,60]])
        self.assertEqual([len(x['co_aligned_termination_other_inverters']) for x in rows],[2,2,2])
        self.assertTrue(all(x['tr_parent'] is None for x in rows))
        self.assertTrue(all(not x['electrical_path_verified'] for x in rows))

    def test_no_gap_bridging(self):
        s=[((100,100),(100,80)),((100,79.1),(100,60))]
        r=trace_converter_inputs([c(1,100)],s)[0]
        self.assertEqual(r['segments_in_run'],1)
        self.assertEqual(r['upstream_terminal_px'],[100,80])

    def test_crossing_no_dot_not_connected(self):
        s=[((100,100),(100,60)),((80,80),(120,80))]
        self.assertEqual(len(conductor_components(s)),2)

    def test_t_junction_unmarked_is_ambiguous_not_auto_bridge(self):
        s=[((100,100),(100,60)),((100,80),(130,80))]
        self.assertEqual(len(conductor_components(s)),2)

    def test_explicit_endpoint_to_endpoint_is_connected(self):
        s=[((100,100),(100,80)),((100,80),(140,80))]
        self.assertEqual(len(conductor_components(s)),1)

    def test_no_assumed_one_to_two_cardinality(self):
        s=[((i*100,100),(i*100,70)) for i in range(1,6)]
        r=trace_converter_inputs([c(i,i*100) for i in range(1,6)],s)
        self.assertEqual(len(r),5)
        self.assertTrue(all(x['tr_parent'] is None for x in r))

    def test_extract_rejects_dashed_and_colored(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'fixture.pdf'
            doc=fitz.open();page=doc.new_page(width=900,height=600)
            page.draw_line((100,80),(100,160),color=(0,0,0),width=1)
            page.draw_line((200,80),(200,160),color=(1,0,0),width=1)
            page.draw_line((300,80),(300,160),color=(0,0,0),width=1,dashes='[2 2] 0')
            doc.save(p);doc.close()
            with fitz.open(p) as d:
                strokes=extract_solid_conductors(d[0])
            self.assertEqual(len(strokes),1)

    def test_no_false_input_if_no_black_conductor(self):
        row=trace_converter_inputs([c(1,100)],[])[0]
        self.assertIsNone(row['upstream_terminal_px'])
        self.assertEqual(row['status'],'NO_UNINTERRUPTED_BLACK_INPUT_LEAD')

    def test_local_cad_source_is_read_only_and_no_txt(self):
        from sld_ci_v04_beta3.tests.test_alpha18_vector_semantics import make_vector_cad
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test_unknown.pdf';make_vector_cad(p)
            h=hashlib.sha256(p.read_bytes()).hexdigest()
            base,imgs,prior,report=inspect_cad_conductor_runs(p)
            self.assertEqual(h,hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertFalse(report['source_ground_truth_used'])
            self.assertFalse(report['source_txt_used'])
            self.assertEqual(report['summary']['tr_parent_connections_verified'],0)
            self.assertIsNone(report['summary']['string_boxes_quantified'])
            out=write_cad_conductor_outputs(base,imgs,prior,report,Path(t)/'out')
            self.assertTrue((out/'alpha20_conduttori_ingresso.json').is_file())
            self.assertTrue((out/'alpha20_morsetti_ingresso.csv').is_file())
            self.assertFalse((out/'alpha20_CU_TR_INV_STR_Box.csv').exists())

if __name__=='__main__':unittest.main()
