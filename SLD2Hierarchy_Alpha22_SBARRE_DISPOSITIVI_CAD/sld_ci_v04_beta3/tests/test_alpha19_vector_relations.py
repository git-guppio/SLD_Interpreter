"""Alpha19 regression: safe geometric hypotheses, never SAP or string-box truth."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sld_ci_v04_beta3.sap.vector_relations_alpha19 import (
    correlate_graphic_candidates, inspect_cad_relations, write_cad_relation_outputs)


def inv(i, x, *, page=1, taps=8):
    return {'page':page,'candidate_id':f'INV{i}',
            'bbox_px':[x,30,x+40,85],'outgoing_branches_observed':taps}


def field(i, x, *, page=1, cells=8, y=130):
    return {'page':page,'field_candidate':i,'graphic_panels':2,
            'compartments_observed':cells,
            'panel_boxes_px':[[x,y,x+65,y+20],[x+5,y+60,x+70,y+80]]}


class Alpha19Tests(unittest.TestCase):
    def setUp(self):
        self.invs=[inv(1,100),inv(2,240),inv(3,380)]
        self.fields=[field(1,10),field(2,210),field(3,410)]

    def test_ordinal_hypotheses_preserve_uncertainty(self):
        rows,pages=correlate_graphic_candidates(self.invs,self.fields)
        self.assertEqual(len(rows),3)
        self.assertEqual([r['field_candidate'] for r in rows],[1,2,3])
        self.assertEqual(pages[0]['proposed_pairs'],3)
        for r in rows:
            self.assertEqual(r['graphic_compartments_observed'],8)
            self.assertTrue(r['branches_equal_compartments'])
            self.assertIsNone(r['inferred_string_boxes'])
            self.assertIsNone(r['tr_parent'])
            self.assertIsNone(r['cu_parent'])
            self.assertFalse(r['electric_path_verified'])

    def test_shuffled_inputs_do_not_change_order(self):
        rows,_=correlate_graphic_candidates(self.invs[::-1],self.fields[::-1])
        self.assertEqual([r['field_candidate'] for r in rows],[1,2,3])

    def test_mismatched_field_count_abstains_all(self):
        rows,pages=correlate_graphic_candidates(self.invs,self.fields[:2])
        self.assertTrue(pages[0]['abstained'])
        self.assertIn('CARDINALITY_MISMATCH',pages[0]['reasons'])
        self.assertTrue(all(r['field_candidate'] is None for r in rows))

    def test_singleton_cannot_create_parent(self):
        rows,pages=correlate_graphic_candidates(self.invs[:1],self.fields[:1])
        self.assertTrue(pages[0]['abstained'])
        self.assertIsNone(rows[0]['field_candidate'])

    def test_different_pages_do_not_connect(self):
        wrong=[field(i,xx,page=2) for i,xx in [(1,10),(2,210),(3,410)]]
        rows,pages=correlate_graphic_candidates(self.invs,wrong)
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['field_candidate'] is None for r in rows))
        self.assertTrue(all(p['abstained'] for p in pages))

    def test_fields_above_modules_not_downstream(self):
        rows,pages=correlate_graphic_candidates(self.invs,[field(i,x,y=60) for i,x in [(1,10),(2,210),(3,410)]])
        self.assertIn('NON_DOWNSTREAM_PANEL',pages[0]['reasons'])
        self.assertTrue(all(r['field_candidate'] is None for r in rows))

    def test_overlapping_fields_are_ambiguous(self):
        rows,pages=correlate_graphic_candidates(self.invs,[field(1,10),field(2,40),field(3,410)])
        self.assertIn('OVERLAPPING_FIELDS',pages[0]['reasons'])
        self.assertTrue(all(r['field_candidate'] is None for r in rows))

    def test_overlapping_inverters_are_ambiguous(self):
        rows,pages=correlate_graphic_candidates([inv(1,100),inv(2,135),inv(3,380)],self.fields)
        self.assertIn('OVERLAPPING_CONVERTERS',pages[0]['reasons'])
        self.assertTrue(all(r['field_candidate'] is None for r in rows))

    def test_count_mismatch_between_taps_and_cells_not_faked(self):
        rows,_=correlate_graphic_candidates([inv(1,100,taps=4),*self.invs[1:]],self.fields)
        self.assertFalse(rows[0]['branches_equal_compartments'])
        self.assertEqual(rows[0]['outgoing_branches_observed'],4)
        self.assertIsNone(rows[0]['inferred_string_boxes'])

    def test_three_plus_inverters_per_transformer_not_restricted(self):
        # No 1:2 TR/inverter or any other cardinality assumptions in matcher.
        invs=[inv(i,i*90) for i in range(1,6)]
        fields=[field(i,i*110) for i in range(1,6)]
        rows,pages=correlate_graphic_candidates(invs,fields)
        self.assertEqual(len(rows),5)
        self.assertEqual(pages[0]['proposed_pairs'],5)
        self.assertTrue(all(r['tr_parent'] is None for r in rows))

    def test_output_csv_does_not_fabricate_sap_devices(self):
        with tempfile.TemporaryDirectory() as t:
            rows,pages=correlate_graphic_candidates(self.invs,self.fields)
            report={'schema':'sld-alpha19-vector-hypotheses/v1',
                    'candidate_graphic_correlations':rows,'page_diagnostics':pages}
            dest=Path(t)
            # Minimal output needs original Alpha18 base for structured writer.
            base={'converter_candidates':[],'downstream_graphic_panels':[],
                  'downstream_field_candidates':[]}
            out=write_cad_relation_outputs(base,[],report,dest)
            path=out/'alpha19_correlazioni_grafiche.csv'
            with path.open(encoding='utf-8-sig') as reader:
                data=list(csv.DictReader(reader,delimiter=';'))
            self.assertEqual(len(data),3)
            self.assertTrue(all(not r['string_box_quantita'] and not r['trasformatore_padre'] for r in data))
            self.assertTrue((out/'alpha18_candidati_vettoriali.json').exists())

    def test_real_vector_pdf_read_only_and_ground_truth_not_used(self):
        # Installed fixture excludes user-provided TXT and source-specific values.
        from sld_ci_v04_beta3.tests.test_alpha18_vector_semantics import make_vector_cad
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'arbitrary_name.pdf'
            make_vector_cad(p)
            before=hashlib.sha256(p.read_bytes()).hexdigest()
            _,_,report=inspect_cad_relations(p)
            self.assertFalse(report['ground_truth_used'])
            self.assertFalse(report['reference_txt_used'])
            self.assertIsNone(report['summary']['verified_string_boxes'])
            self.assertEqual(before,hashlib.sha256(p.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
