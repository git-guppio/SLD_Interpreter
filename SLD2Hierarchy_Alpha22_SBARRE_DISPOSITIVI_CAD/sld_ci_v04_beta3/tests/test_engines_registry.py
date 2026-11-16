"""Registro dei motori e modello dati normalizzato (priorita 4)."""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from sld_ci_v04_beta3.engines import (ENGINES, Hierarchy, Status, engine_by_mode,
                                      read_evidence_csv, select_engine)
from sld_ci_v04_beta3.engines.base import DocumentProbe
from sld_ci_v04_beta3.engines.model import (NORMALIZED_CSV, NORMALIZED_JSON,
                                            normalize_parent_status, normalize_sb_status)
from sld_ci_v04_beta3.engines.recognizers import (CadVectorRecognizer, IndexedTagRecognizer,
                                                  LabelFirstRecognizer, LvlRecognizer)

EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'


class _FakeProbe:
    def __init__(self, text='', lvl=False, vector=False):
        self.text, self.has_lvl_family, self.is_vector_only = text, lvl, vector


class RegistryTests(unittest.TestCase):
    def test_modes_are_unique_and_fallback_is_last(self):
        modes = [e.mode for e in ENGINES]
        self.assertEqual(len(modes), len(set(modes)))
        self.assertIsInstance(ENGINES[-1], LabelFirstRecognizer)
        self.assertEqual(modes, ['alpha15-indexed', 'alpha16-lvl', 'alpha21-cad', 'alpha12'])

    def test_engine_by_mode(self):
        self.assertIsInstance(engine_by_mode('alpha21-cad'), CadVectorRecognizer)
        with self.assertRaises(KeyError):
            engine_by_mode('alpha99')

    def test_matching_rules(self):
        both = _FakeProbe(text='CLT-TPO-01-01\nCLT-INV-01-01')
        self.assertTrue(IndexedTagRecognizer().matches(both))
        self.assertFalse(IndexedTagRecognizer().matches(_FakeProbe(text='CLT-INV-01-01')))
        self.assertTrue(LvlRecognizer().matches(_FakeProbe(lvl=True)))
        self.assertTrue(CadVectorRecognizer().matches(_FakeProbe(vector=True)))
        self.assertTrue(LabelFirstRecognizer().matches(_FakeProbe()))

    def test_probe_is_lazy(self):
        # Nessuna apertura del PDF finche una proprieta non serve.
        probe = DocumentProbe('non_esiste.pdf')
        self.assertEqual(probe.pdf_path.name, 'non_esiste.pdf')

    def test_review_forces_label_first_engine(self):
        self.assertIsInstance(select_engine('qualsiasi.pdf', review=Path('r.json')), LabelFirstRecognizer)

    def test_commands(self):
        out, pdf = Path('out'), Path('a.pdf')
        cmd = CadVectorRecognizer().build_command(pdf, 'PV1', out, Path('rev.json'), executable='py')
        self.assertEqual(cmd[:3], ['py', '-m', 'sld_ci_v04_beta3.alpha22_cli'])
        self.assertEqual(cmd[-2:], ['--review-json', 'rev.json'])
        # I motori a tag non accettano review: non deve finire nella riga di comando.
        cmd = IndexedTagRecognizer().build_command(pdf, 'PV1', out, Path('rev.json'), executable='py')
        self.assertNotIn('--review-json', cmd)
        self.assertIn('sld_ci_v04_beta3.alpha15_cli', cmd)
        cmd = LvlRecognizer().build_command(pdf, 'PV1', out, executable='py')
        self.assertIn('sld_ci_v04_beta3.alpha16_cli', cmd)


class StatusTests(unittest.TestCase):
    def test_parent_mapping(self):
        self.assertIs(normalize_parent_status('CONFERMATO_HITL'), Status.OPERATOR_CONFIRMED)
        self.assertIs(normalize_parent_status('CANDIDATO_PER_CODIFICA'), Status.INFERRED)
        self.assertIs(normalize_parent_status('NON_RISOLTO'), Status.UNRESOLVED)
        # Codice sconosciuto: prudenza, mai "confermato".
        self.assertIs(normalize_parent_status('NUOVO_CODICE'), Status.UNRESOLVED)
        self.assertIs(normalize_parent_status(None), Status.UNRESOLVED)

    def test_string_box_mapping(self):
        self.assertIs(normalize_sb_status('QUANTITA_DA_ETICHETTA', 10), Status.OBSERVED)
        # Quantita assente = non risolta, anche se il codice dice altro.
        self.assertIs(normalize_sb_status('QUANTITA_DA_ETICHETTA', None), Status.UNRESOLVED)
        self.assertIs(normalize_sb_status('SEQUENZA_BOX_INCOMPLETA', 4), Status.UNRESOLVED)


class EvidenceCsvTests(unittest.TestCase):
    CASES = {
        'ALPHA12_PV11_VERIFICA/ESEMPIO_evidenze.csv': Status.INFERRED,
        'ALPHA15_MULTI_SLD/PV5/alpha15_evidenze.csv': Status.INFERRED,
        'ALPHA16_PV8/alpha16_evidenze.csv': Status.INFERRED,
        'ALPHA21_SETTIMO_REFERENZA/alpha21_evidenze.csv': Status.OPERATOR_CONFIRMED,
    }

    def test_all_engine_formats_are_read_consistently(self):
        for rel, expected_parent in self.CASES.items():
            with self.subTest(rel=rel):
                path = EXAMPLES / rel
                rows = read_evidence_csv(path)
                with path.open(encoding='utf-8-sig') as handle:
                    raw = list(csv.DictReader(handle, delimiter=';'))
                self.assertEqual(len(rows), len(raw))
                self.assertEqual([r.string_boxes for r in rows],
                                 [int(x['STR_Box']) if x['STR_Box'] else None for x in raw])
                self.assertIs(rows[0].parent_status, expected_parent)
                self.assertTrue(rows[0].evidence)
                self.assertTrue(rows[0].source_asset_id)

    def test_settimo_reference_summary(self):
        rows = read_evidence_csv(EXAMPLES / 'ALPHA21_SETTIMO_REFERENZA/alpha21_evidenze.csv')
        s = Hierarchy('alpha21-cad', 'CI::PV13', 'x.pdf', rows).summary()
        self.assertEqual((s['CU'], s['TR'], s['righe_inverter']), (1, 1, 3))
        self.assertEqual(s['string_box_totale_risolto'], 24)
        self.assertEqual(s['parent_confermati_operatore'], 3)

    def test_unknown_format_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'x.csv'
            bad.write_text('a;b\n1;2\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_evidence_csv(bad)


class LoadAndWriteTests(unittest.TestCase):
    def test_round_trip_from_engine_output_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            src = EXAMPLES / 'ALPHA16_PV8'
            shutil.copy(src / 'alpha16_evidenze.csv', run)
            shutil.copy(src / 'alpha16_diagnostica.json', run)
            hierarchy = engine_by_mode('alpha16-lvl').load_hierarchy(run)
            self.assertTrue(hierarchy.plant_id.startswith('CI::'))
            paths = hierarchy.write(run)
            self.assertEqual({p.name for p in paths.values()}, {NORMALIZED_CSV, NORMALIZED_JSON})
            data = json.loads(paths['json'].read_text(encoding='utf-8'))
            self.assertEqual(data['schema'], 'sld-normalized-hierarchy/v1')
            self.assertEqual(len(data['rows']), hierarchy.summary()['righe_inverter'])
            with paths['csv'].open(encoding='utf-8-sig') as handle:
                self.assertEqual(len(list(csv.reader(handle, delimiter=';'))) - 1, len(data['rows']))

    def test_cad_without_review_gives_empty_hierarchy(self):
        # Senza review operatore il motore CAD non produce alpha21_evidenze.csv.
        with tempfile.TemporaryDirectory() as tmp:
            hierarchy = engine_by_mode('alpha21-cad').load_hierarchy(Path(tmp))
            self.assertEqual(hierarchy.rows, [])


if __name__ == '__main__':
    unittest.main()
