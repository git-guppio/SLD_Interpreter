"""Alpha14 GUI workflow: safety checks can run without launching Windows UI."""
import json
import tempfile
import unittest
from pathlib import Path

from sld_ci_v04_beta3.sap_workbench_alpha14 import (
    next_run_directory, load_report_folder, portfolio_rows,
    write_portfolio_csv, validate_alpha13_review, REPORT_NAME,
)
from sld_ci_v04_beta3.sap.evidence_visual_alpha13 import VisualReviewLedger


EXAMPLE = Path(__file__).resolve().parents[2] / 'examples' / 'ALPHA12_PV11_VERIFICA' / 'ESEMPIO_riepilogo.json'
REAL_PDF = Path('/mnt/data/PV11_Pampa_Norte.pdf')


class Alpha14WorkbenchTests(unittest.TestCase):
    def test_new_run_preserves_existing_runs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = next_run_directory(root, 'PV11', now='20261111_093000')
            old.mkdir(parents=True)
            newer = next_run_directory(root, 'PV11', now='20261111_093000')
            self.assertEqual(newer.name, '20261111_093000_02')
            self.assertTrue(old.is_dir())
            self.assertFalse(newer.exists())

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for plant in ('../../other', 'A/B', 'A\\B', 'A B', ''):
                with self.subTest(plant=plant), self.assertRaises(ValueError):
                    next_run_directory(Path(d), plant)

    def test_missing_report_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'alpha12_riepilogo'):
                load_report_folder(Path(d))

    def test_portfolio_only_counts_real_reports(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = next_run_directory(root, 'PV11', now='20261111_093000')
            folder.mkdir(parents=True)
            (folder / REPORT_NAME).write_bytes(EXAMPLE.read_bytes())
            rows=portfolio_rows(root)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['INV_candidati'],88)
            self.assertEqual(rows[0]['SB_quantita_documentate'],923)
            self.assertEqual(rows[0]['import_Matrix_FLOW_certificato'],'NO')
            other=next_run_directory(root,'PV13',now='20261111_093001')
            other.mkdir(parents=True)
            (other / REPORT_NAME).write_text('not json')
            self.assertEqual(len(portfolio_rows(root)),1)
            csv_path, count = write_portfolio_csv(root)
            self.assertEqual(count,1)
            self.assertIn('PV11_Pampa_Norte',csv_path.read_text(encoding='utf-8-sig'))

    def test_legacy_nonvisual_hitl_refused(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/REPORT_NAME).write_bytes(EXAMPLE.read_bytes())
            (folder/'alpha13_operator_review_APPROVED.json').write_text(json.dumps({
                'schema':'sld-sap-alpha10-reviewed-parentage/v1',
                'plant_id':'CI::PV11_Pampa_Norte',
                'confirmed_tr_inverter_groups':[{'cu_ids':[1,2], 'transformer_slot':1,'inverter_slots':[1]}]
            }))
            with self.assertRaises(ValueError):
                validate_alpha13_review(folder,REAL_PDF)

    @unittest.skipUnless(REAL_PDF.is_file(), 'File PV11 non presente')
    def test_scoped_visual_hitl_accepted_only_for_exact_source(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/REPORT_NAME).write_bytes(EXAMPLE.read_bytes())
            ledger=VisualReviewLedger(folder/REPORT_NAME,REAL_PDF,folder)
            candidate=ledger.records[0]
            ledger.set_decision(candidate['asset_id_originale'],'CONFERMATO_VISIVO')
            ledger.save()
            path,count=validate_alpha13_review(folder,REAL_PDF)
            self.assertEqual(count,1)
            self.assertTrue(path.is_file())
            data=json.loads((folder/REPORT_NAME).read_text())
            data['summary']['inverters']=99
            (folder/REPORT_NAME).write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'non corrisponde'):
                validate_alpha13_review(folder,REAL_PDF)


if __name__=='__main__':unittest.main()
