"""Bozza di review CAD precompilata dai percorsi (priorita 6)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from sld_ci_v04_beta3.review_editor_gui import REVIEW_NAME, open_review_editor, save_review
from sld_ci_v04_beta3.sap.cad_qps_hierarchy_alpha21 import validate_operator_review
from sld_ci_v04_beta3.sap.cad_review_draft import (AUDIT_FILE, DRAFT_NAME, QPS_FILE, build_review_draft,
                                                   finalize_review, validate_against_run)

EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'
A21 = json.loads((EXAMPLES / 'ALPHA21_SETTIMO_REFERENZA' / QPS_FILE).read_text(encoding='utf-8'))
MANUAL = json.loads((EXAMPLES / 'SETTIMO_TOP_SCHEMA_CONFERMATO_OPERATORE.json').read_text(encoding='utf-8'))


def audit(windings):
    """windings: {INV_GRAFICO_00n: (path_a, path_b)}"""
    return {'pages': [{'page': 1, 'tr_inverter_paths_through_devices': [
        {'converter_candidate_id': c, 'chain': [{'element': 'TR_WINDING_PAIR', 'source_paths': list(w)}]}
        for c, w in windings.items()]}]}


ALL_SAME = audit({f'INV_GRAFICO_00{i}': (7, 9) for i in (1, 2, 3)})


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf = Path(self.tmp.name) / 'cad.pdf'
        self.pdf.write_bytes(b'%PDF-1.4 sintetico')

    def finalize(self, draft, **kw):
        return finalize_review(draft, operator_evidence=kw.pop('evidence', 'Verifica SLD p1 del 16/11/2026'),
                               confirm_qps_is_string_box=kw.pop('sb', True),
                               confirm_numbering=kw.pop('num', True), **kw)

    def validate(self, review):
        validate_operator_review(review, self.pdf, review['plant_id'], A21['qps_sequences'], [0] * 3)

    def test_draft_matches_operator_review_for_settimo_topology(self):
        draft = build_review_draft(self.pdf, 'PV13_Settimo_Torinese', A21, ALL_SAME)
        review = self.finalize(draft)
        self.assertEqual(review['parent_confirmations'], MANUAL['parent_confirmations'])
        self.assertFalse(any(k.startswith('_') for k in review))
        self.validate(review)

    def test_unconfirmed_draft_is_never_valid(self):
        draft = build_review_draft(self.pdf, 'PV13_Settimo_Torinese', A21, ALL_SAME)
        self.assertFalse(draft['operator_confirmed'])
        with self.assertRaises(ValueError):
            self.validate(draft)
        for kw in ({'sb': False}, {'num': False}, {'evidence': 'ok'}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.validate(self.finalize(draft, **kw))

    def test_two_windings_give_two_trs(self):
        two = audit({'INV_GRAFICO_001': (7, 9), 'INV_GRAFICO_002': (7, 9), 'INV_GRAFICO_003': (20, 22)})
        rows = build_review_draft(self.pdf, 'X', A21, two)['parent_confirmations']
        self.assertEqual([r['TR'] for r in rows], [1, 1, 2])

    def test_inverter_without_path_must_be_filled_by_operator(self):
        partial = audit({'INV_GRAFICO_001': (7, 9), 'INV_GRAFICO_002': (7, 9)})
        draft = build_review_draft(self.pdf, 'X', A21, partial)
        last = draft['parent_confirmations'][-1]
        self.assertIsNone(last['TR'])
        self.assertEqual(last['_fonte_TR'], 'DA_COMPILARE')
        with self.assertRaises(ValueError):
            self.validate(self.finalize(draft))

    def test_incomplete_qps_groups_are_excluded(self):
        a21 = json.loads(json.dumps(A21))
        a21['qps_sequences'][2]['sequence_complete'] = False
        draft = build_review_draft(self.pdf, 'X', a21, ALL_SAME)
        self.assertEqual([r['qps_group'] for r in draft['parent_confirmations']], [1, 2])
        self.assertEqual(draft['_bozza']['gruppi_QPS_incompleti_esclusi'], 1)

    def test_validate_against_run_folder_and_save(self):
        run = Path(self.tmp.name) / 'run'
        run.mkdir()
        shutil.copy(EXAMPLES / 'ALPHA21_SETTIMO_REFERENZA' / QPS_FILE, run / QPS_FILE)
        review = self.finalize(build_review_draft(self.pdf, 'PV13_Settimo_Torinese', A21, ALL_SAME))
        self.assertTrue(validate_against_run(review, self.pdf, run))
        path = save_review(review, run)
        self.assertEqual(path.name, REVIEW_NAME)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), review)


class EditorWindowSmokeTests(unittest.TestCase):
    def test_window_opens_and_writes_draft(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as exc:  # Tk non disponibile (CI, sessione senza display)
            self.skipTest(f'Tk non disponibile: {exc}')
        root.withdraw()
        with tempfile.TemporaryDirectory() as tmp:
            run, pdf = Path(tmp), Path(tmp) / 'cad.pdf'
            pdf.write_bytes(b'%PDF-1.4 sintetico')
            shutil.copy(EXAMPLES / 'ALPHA21_SETTIMO_REFERENZA' / QPS_FILE, run / QPS_FILE)
            (run / AUDIT_FILE).write_text(json.dumps(ALL_SAME), encoding='utf-8')
            try:
                win = open_review_editor(root, run, pdf)
                root.update_idletasks()
                self.assertTrue((run / DRAFT_NAME).is_file())
                self.assertFalse((run / REVIEW_NAME).exists())   # niente salvataggio senza conferma
                win.destroy()
            finally:
                root.destroy()


if __name__ == '__main__':
    unittest.main()
