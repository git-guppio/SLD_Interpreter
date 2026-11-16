"""Archi-dispositivo: si attraversa un apparecchio solo con tratti disegnati (priorita 5)."""
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from sld_ci_v04_beta3.sap.cad_bus_provenance_alpha22 import (
    audit_bus_and_winding, audit_cad_pdf, detect_series_apparatus_motifs, open_gaps,
    write_alpha22_reports)
from sld_ci_v04_beta3.sap.cad_device_edges import (
    EDGE_OK, PATH_OK, collect_axis_evidence, collect_vertical_strokes, cross_check_review,
    device_edges, device_type_candidate, tr_inverter_paths, uncovered_intervals)
from sld_ci_v04_beta3.tests.test_alpha22_bus_provenance import setup

GREEN, MAGENTA, ORANGE = (0, 1, 0), (1, 0, 1), (1, .5, 0)
XS = (40, 60, 80)                 # assi degli inverter nello scenario setup()
TR_SYMBOL, INV_SYMBOL_Y = (60, 54.6), 67.5


def draw_symbols(page, *, extra_ambiguous=False):
    for xx, yy in [TR_SYMBOL] + [(x, INV_SYMBOL_Y) for x in XS]:
        page.draw_rect(fitz.Rect(xx - 1, yy - 1.6, xx + 1, yy + 1.6), color=GREEN, width=.2)
        for k in range(2):
            page.draw_line(fitz.Point(xx - .2, yy - .8 + k * .7), fitz.Point(xx + .2, yy - .7 + k * .7),
                           color=MAGENTA, width=.13)


def draw_leads(page, *, skip_inverter=None, dashed=False, short_by=0.0):
    """Tratti colorati che collegano capo -> simbolo -> capo lungo l'asse."""
    segments = [((60, 52), (60, 53.0)), ((60, 56.2), (60, 60))]          # TR
    for x in XS:
        if x == skip_inverter:
            continue
        segments += [((x, 60), (x, 65.9 - short_by)), ((x, 69.1), (x, 73))]
    for a, b in segments:
        shape = page.new_shape()
        shape.draw_line(fitz.Point(*a), fitz.Point(*b))
        shape.finish(color=ORANGE, width=.3, dashes='[1 1] 0' if dashed else None)
        shape.commit()


def scene(**kwargs):
    doc = fitz.open()
    page = doc.new_page(width=1000, height=1000)
    draw_symbols(page)
    leads = kwargs.pop('leads', True)
    if leads:
        draw_leads(page, **kwargs)
    s, r, w = setup()
    audit = audit_bus_and_winding(s, r, w)
    audit['source_series_device_visual_motifs'] = detect_series_apparatus_motifs(page, audit)
    return doc, page, audit


def edges_for(page, audit):
    return device_edges(collect_vertical_strokes(page), open_gaps(audit),
                        audit['source_series_device_visual_motifs'])


class IntervalTests(unittest.TestCase):
    def test_uncovered(self):
        self.assertEqual(uncovered_intervals([(0, 4), (4.3, 10)], 0, 10, .55), [])
        self.assertEqual(uncovered_intervals([(0, 4), (6, 10)], 0, 10, .55), [(4, 6)])
        self.assertEqual(uncovered_intervals([], 0, 10, .55), [(0, 10)])
        self.assertEqual(uncovered_intervals([(2, 10)], 0, 10, .55), [(0, 2)])
        self.assertEqual(uncovered_intervals([], 0, .3, .55), [])   # gap sotto tolleranza


class DeviceEdgeTests(unittest.TestCase):
    def test_drawn_leads_create_device_edges_and_paths(self):
        doc, page, audit = scene()
        try:
            edges = edges_for(page, audit)
            self.assertEqual(len(edges), 4)
            self.assertTrue(all(e['status'] == EDGE_OK and e['device_edge_created'] for e in edges))
            self.assertTrue(all(not e['device_type_classified'] for e in edges))
            self.assertTrue(all(e['upstream_lead_source_path_indices'] for e in edges))
            paths = tr_inverter_paths(audit, edges)
            self.assertEqual([p['converter_candidate_id'] for p in paths], ['INV_1', 'INV_2', 'INV_3'])
            for p in paths:
                self.assertEqual(p['status'], PATH_OK)
                self.assertEqual(p['parent_status'], 'inferred')
                self.assertFalse(p['electrical_path_verified'])
                self.assertEqual([c['element'] for c in p['chain']],
                                 ['TR_WINDING_PAIR', 'TR_SECONDARY_WIRE', 'DEVICE', 'BUSBAR',
                                  'DEVICE', 'INVERTER_INPUT_LEAD'])
        finally:
            doc.close()

    def test_symbol_without_leads_is_not_traversed(self):
        doc, page, audit = scene(leads=False)
        try:
            edges = edges_for(page, audit)
            self.assertTrue(all(e['status'] == 'DEVICE_SYMBOL_NOT_ATTACHED' for e in edges))
            self.assertTrue(all(e['uncovered_upstream_px'] or e['uncovered_downstream_px'] for e in edges))
            self.assertEqual(tr_inverter_paths(audit, edges), [])
        finally:
            doc.close()

    def test_small_hole_beyond_tolerance_keeps_gap_open(self):
        doc, page, audit = scene(short_by=1.0)   # 1 px non disegnato sopra ogni simbolo inverter
        try:
            edges = {e['downstream_entity']: e for e in edges_for(page, audit)}
            self.assertTrue(edges['TR_WINDING_CANDIDATE']['device_edge_created'])
            for inv in ('INV_1', 'INV_2', 'INV_3'):
                self.assertFalse(edges[inv]['device_edge_created'])
                self.assertEqual(edges[inv]['uncovered_upstream_px'], [(64.9, 65.9)])
        finally:
            doc.close()

    def test_dashed_lines_are_not_conductors(self):
        doc, page, audit = scene(dashed=True)
        try:
            self.assertFalse(any(e['device_edge_created'] for e in edges_for(page, audit)))
        finally:
            doc.close()

    def test_missing_branch_only_drops_that_inverter(self):
        doc, page, audit = scene(skip_inverter=80)
        try:
            paths = tr_inverter_paths(audit, edges_for(page, audit))
            self.assertEqual([p['converter_candidate_id'] for p in paths], ['INV_1', 'INV_2'])
        finally:
            doc.close()

    def test_no_tr_edge_means_no_path(self):
        doc, page, audit = scene()
        try:
            edges = [e for e in edges_for(page, audit) if e['gap_type'] != 'TR_SECONDARY_TO_BUSBAR']
            self.assertEqual(tr_inverter_paths(audit, edges), [])
        finally:
            doc.close()

    def test_ambiguous_or_missing_symbol_abstains(self):
        s, r, w = setup()
        audit = audit_bus_and_winding(s, r, w)
        gaps = open_gaps(audit)
        motif = {'gap_type': 'BUSBAR_TO_INVERTER', 'downstream_entity': 'INV_1',
                 'status': 'AMBIGUOUS_MULTIPLE_SYMBOLS_IN_GAP'}
        edges = device_edges([], gaps, [motif])
        self.assertTrue(all(e['status'] == 'NO_UNIQUE_DEVICE_SYMBOL_IN_GAP' for e in edges))


class SmallPageScaleTests(unittest.TestCase):
    def test_motifs_found_on_pages_smaller_than_1000pt(self):
        # Prima della correzione la scala dei simboli (1000/lato = 2) non
        # coincideva con quella dei conduttori (1) e i simboli non erano trovati.
        doc = fitz.open()
        page = doc.new_page(width=500, height=500)
        draw_symbols(page)
        s, r, w = setup()
        audit = audit_bus_and_winding(s, r, w)
        try:
            self.assertEqual(len(detect_series_apparatus_motifs(page, audit)), 4)
        finally:
            doc.close()


class EndToEndAuditTests(unittest.TestCase):
    def test_audit_and_reports_on_synthetic_settimo_like_pdf(self):
        s, runs, _ = setup()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / 'cad.pdf'
            doc = fitz.open()
            page = doc.new_page(width=1000, height=1000)
            for a, b in s:   # conduttori neri: sbarra, ingressi inverter, filo secondario TR
                page.draw_line(fitz.Point(*a), fitz.Point(*b), color=(0, 0, 0), width=.5)
            draw_symbols(page)
            draw_leads(page)
            doc.save(str(pdf_path))
            doc.close()
            alpha20 = {'input_conductor_runs': runs,
                       'transformer_winding_geometry_evidence': [{'page': 1, 'local_upstream_winding_hypotheses': {
                           'candidates': [{'center_px': [60, 0], 'source_path_indices': [10, 12]}]}}]}
            report = audit_cad_pdf(pdf_path, alpha20)
            summary = report['summary']
            self.assertEqual(summary['device_edges_source_connected'], 4)
            self.assertEqual(summary['tr_inverter_paths_through_unclassified_devices'], 3)
            self.assertEqual(summary['tr_inverter_automatically_electrically_verified'], 0)
            self.assertIn('device_axis_tolerance', report['thresholds'])
            out = write_alpha22_reports(pdf_path, report, tmp)
            relations = out['csv'].read_text(encoding='utf-8-sig')
            self.assertEqual(relations.count('ATTRAVERSATE_CON_ARCHI_DISPOSITIVO'), 3)
            self.assertNotIn('NON_PONTICELLATE', relations)
            devices = out['dispositivi'].read_text(encoding='utf-8-sig').splitlines()
            self.assertTrue(all(';NO;SI;' in line for line in devices[1:]))


def _line(page, a, b, color=ORANGE, dashed=False):
    shape = page.new_shape()
    shape.draw_line(fitz.Point(*a), fitz.Point(*b))
    shape.finish(color=color, width=.3, closePath=False, dashes='[1 1] 0' if dashed else None)
    shape.commit()


def draw_iec_branch(page, x, *, x_offset=0.0, open_triangle=False, blade_shift=0.0, dashed=False):
    """Ramo sbarra->inverter come su Settimo: tratto, triangolo estraibile,
    tratto, [simbolo], tratto, lama, X sul capo verso l'inverter."""
    _line(page, (x, 60), (x, 62.5))
    tri = [((x, 62.5), (x + .57, 64.0)), ((x + .57, 64.0), (x - .57, 64.0)), ((x - .57, 64.0), (x, 62.5))]
    shape = page.new_shape()
    for a, b in (tri[:2] if open_triangle else tri):
        shape.draw_line(fitz.Point(*a), fitz.Point(*b))
    shape.finish(color=(0, 0, 0), width=.3, closePath=False, dashes='[1 1] 0' if dashed else None)
    shape.commit()
    _line(page, (x, 64.0), (x, 65.9))
    _line(page, (x, 69.1), (x, 69.9))
    _line(page, (x + blade_shift, 69.9), (x + blade_shift - 1.46, 72.3), color=(0, 1, 1))
    cx = x + x_offset
    shape = page.new_shape()
    shape.draw_line(fitz.Point(cx - .39, 72.31), fitz.Point(cx + .39, 73.09))
    shape.draw_line(fitz.Point(cx - .39, 73.09), fitz.Point(cx + .39, 72.31))
    shape.finish(color=(0, 0, 0), width=.3, closePath=False, dashes='[1 1] 0' if dashed else None)
    shape.commit()


class IecPrimitiveTests(unittest.TestCase):
    """Copertura dei gap tramite primitive IEC 60617 sull'asse (caso reale Settimo/PV3)."""

    def _scene(self, **branch):
        doc = fitz.open()
        page = doc.new_page(width=1000, height=1000)
        draw_symbols(page)
        _line(page, (60, 52), (60, 53.0))
        _line(page, (60, 56.2), (60, 60))
        for x in XS:
            draw_iec_branch(page, x, **branch)
        s, r, w = setup()
        audit = audit_bus_and_winding(s, r, w)
        audit['source_series_device_visual_motifs'] = detect_series_apparatus_motifs(page, audit)
        edges = device_edges(collect_axis_evidence(page), open_gaps(audit),
                             audit['source_series_device_visual_motifs'])
        doc.close()
        return audit, {e['downstream_entity']: e for e in edges}

    def test_withdrawable_breaker_primitives_close_the_gap(self):
        audit, edges = self._scene()
        for inv in ('INV_1', 'INV_2', 'INV_3'):
            e = edges[inv]
            self.assertTrue(e['device_edge_created'], e)
            self.assertEqual(e['device_type_candidate'], 'INTERRUTTORE_ESTRAIBILE')
            self.assertFalse(e['device_type_classified'])
            self.assertEqual(sorted(c['kind'] for c in e['device_components']),
                             ['BREAKER_CONTACT_X', 'SWITCH_BLADE', 'WITHDRAWABLE_CONTACT'])
        self.assertEqual(len(tr_inverter_paths(audit, list(edges.values()))), 3)

    def test_x_off_axis_does_not_cover(self):
        _, edges = self._scene(x_offset=1.0)
        self.assertFalse(any(edges[i]['device_edge_created'] for i in ('INV_1', 'INV_2', 'INV_3')))

    def test_open_triangle_is_not_a_contact(self):
        _, edges = self._scene(open_triangle=True)
        e = edges['INV_2']
        self.assertFalse(e['device_edge_created'])
        self.assertEqual(e['uncovered_upstream_px'], [(62.5, 64.0)])

    def test_blade_with_both_ends_off_axis_does_not_cover(self):
        _, edges = self._scene(blade_shift=3.0)   # entrambi i capi a >= 1.5 px dall'asse
        self.assertFalse(edges['INV_2']['device_edge_created'])

    def test_dashed_primitives_ignored(self):
        _, edges = self._scene(dashed=True)
        self.assertFalse(edges['INV_2']['device_edge_created'])

    def test_type_candidate_rules(self):
        self.assertEqual(device_type_candidate(['SWITCH_BLADE']), 'SEZIONATORE_O_IMS')
        self.assertEqual(device_type_candidate(['SWITCH_BLADE', 'WITHDRAWABLE_CONTACT']),
                         'SEZIONATORE_O_IMS_ESTRAIBILE')
        self.assertEqual(device_type_candidate(['BREAKER_CONTACT_X', 'SWITCH_BLADE']), 'INTERRUTTORE')
        self.assertIsNone(device_type_candidate(['BREAKER_CONTACT_X']))
        self.assertIsNone(device_type_candidate([]))


class ReviewCrossCheckTests(unittest.TestCase):
    """La review non viene mai modificata: si confronta soltanto con il disegno."""

    def _report(self, connected=('INV_GRAFICO_001', 'INV_GRAFICO_002', 'INV_GRAFICO_003')):
        paths = [{'converter_candidate_id': c, 'chain': [{'element': 'TR_WINDING_PAIR', 'source_paths': [7, 9]}]}
                 for c in connected]
        return {'pages': [{'page': 1, 'tr_inverter_paths_through_devices': paths}]}

    def _alpha21(self):
        return {'qps_sequences': [{'qps_group': g, 'converter_candidate_id': f'INV_GRAFICO_{g:03d}'}
                                  for g in (1, 2, 3)]}

    def _review(self, trs=(1, 1, 1)):
        return {'parent_confirmations': [{'qps_group': g, 'CU': 1, 'TR': tr, 'INV': g}
                                         for g, tr in zip((1, 2, 3), trs)]}

    def test_settimo_like_review_supported_by_paths(self):
        rows = cross_check_review(self._review(), self._alpha21(), self._report())
        self.assertEqual([r['status'] for r in rows], ['SUPPORTATA_DA_PERCORSO'] * 3)
        self.assertEqual(rows[0]['automatic_winding'], [7, 9])

    def test_review_splitting_one_winding_into_two_trs_is_flagged(self):
        rows = cross_check_review(self._review(trs=(1, 1, 2)), self._alpha21(), self._report())
        self.assertEqual([r['status'] for r in rows], ['IN_CONFLITTO_CON_PERCORSO'] * 3)

    def test_missing_path_is_not_an_error(self):
        rows = cross_check_review(self._review(), self._alpha21(),
                                  self._report(connected=('INV_GRAFICO_001', 'INV_GRAFICO_002')))
        self.assertEqual([r['status'] for r in rows],
                         ['SUPPORTATA_DA_PERCORSO', 'SUPPORTATA_DA_PERCORSO', 'SENZA_PERCORSO_AUTOMATICO'])

    def test_no_review_no_rows_and_csv_written_only_with_checks(self):
        self.assertEqual(cross_check_review(None, self._alpha21(), self._report()), [])
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'x.pdf'
            pdf.write_bytes(b'%PDF-stub')
            report = {'pages': [], 'operator_review_cross_check':
                      cross_check_review(self._review(), self._alpha21(), self._report())}
            out = write_alpha22_reports(pdf, report, tmp)
            text = out['confronto_review'].read_text(encoding='utf-8-sig')
            self.assertEqual(text.count('SUPPORTATA_DA_PERCORSO'), 3)
            self.assertNotIn('confronto_review', write_alpha22_reports(pdf, {'pages': []}, Path(tmp) / 'b'))


if __name__ == '__main__':
    unittest.main()
