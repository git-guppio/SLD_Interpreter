"""Soglie CAD configurabili: default invariati, override, validazione."""
import json
import tempfile
import unittest
from pathlib import Path

import fitz

from sld_ci_v04_beta3.sap.cad_bus_provenance_alpha22 import (
    audit_bus_and_winding, detect_series_apparatus_motifs)
from sld_ci_v04_beta3.sap.cad_thresholds import DEFAULT, CadBusThresholds
from sld_ci_v04_beta3.tests.test_alpha22_bus_provenance import setup

PROFILE = Path(__file__).resolve().parents[2] / 'config' / 'soglie_cad_default.json'


class ThresholdLoadingTests(unittest.TestCase):
    def test_default_profile_file_matches_code_defaults(self):
        self.assertEqual(CadBusThresholds.load(PROFILE), DEFAULT)
        self.assertEqual(CadBusThresholds.load(None), DEFAULT)

    def test_partial_override(self):
        t = CadBusThresholds.from_mapping({'bus_max_gap': 25, 'series_outline_color': [0, .5, 0]})
        self.assertEqual(t.bus_max_gap, 25.0)
        self.assertEqual(t.series_outline_color, (0.0, 0.5, 0.0))
        self.assertEqual(t.bus_min_span, DEFAULT.bus_min_span)

    def test_invalid_profiles_rejected(self):
        for bad in ({'bus_max_gapp': 3}, {'bus_max_gap': -1}, {'bus_max_gap': '19'},
                    {'bus_max_gap': True}, {'series_outline_color': [0, 2, 0]},
                    {'series_outline_color': [0, 1]}, {'bus_ambiguous_ratio': 1.5}, []):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                CadBusThresholds.from_mapping(bad)

    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'p.json'
            path.write_text(json.dumps({'winding_max_wire_gap': 30}), encoding='utf-8')
            self.assertEqual(CadBusThresholds.load(path).winding_max_wire_gap, 30.0)


class ThresholdBehaviourTests(unittest.TestCase):
    def test_default_and_explicit_default_give_same_audit(self):
        s, r, w = setup()
        self.assertEqual(audit_bus_and_winding(s, r, w),
                         audit_bus_and_winding(s, r, w, thresholds=CadBusThresholds()))

    def test_tighter_gap_makes_engine_abstain(self):
        # Nello scenario sintetico i morsetti distano 13 px dalla sbarra.
        s, r, w = setup()
        self.assertIsNotNone(audit_bus_and_winding(s, r, w)['busbar_evidence']['bus'])
        tight = CadBusThresholds.from_mapping({'bus_max_gap': 10})
        result = audit_bus_and_winding(s, r, w, thresholds=tight)
        self.assertIsNone(result['busbar_evidence']['bus'])
        self.assertEqual(result['tr_inverter_automatically_verified'], 0)

    def test_series_motif_colors_come_from_profile(self):
        doc = fitz.open()
        page = doc.new_page(width=1000, height=1000)
        s, r, w = setup()
        audit = audit_bus_and_winding(s, r, w)
        outline, contact = (0, .5, 1), (1, .5, 0)   # palette diversa da verde/magenta
        for xx, yy in [(60, 54.6), (40, 67.5), (60, 67.5), (80, 67.5)]:
            page.draw_rect(fitz.Rect(xx - 1, yy - 1.6, xx + 1, yy + 1.6), color=outline, width=.2)
            for k in range(2):
                page.draw_line(fitz.Point(xx - .2, yy - .8 + k * .7), fitz.Point(xx + .2, yy - .7 + k * .7),
                               color=contact, width=.13)
        try:
            self.assertEqual(detect_series_apparatus_motifs(page, audit), [])
            profile = CadBusThresholds.from_mapping({'series_outline_color': list(outline),
                                                     'series_contact_color': list(contact)})
            items = detect_series_apparatus_motifs(page, audit, profile)
            self.assertEqual(len(items), 4)
            self.assertTrue(all(not x['device_edge_created'] for x in items))
        finally:
            doc.close()


if __name__ == '__main__':
    unittest.main()
