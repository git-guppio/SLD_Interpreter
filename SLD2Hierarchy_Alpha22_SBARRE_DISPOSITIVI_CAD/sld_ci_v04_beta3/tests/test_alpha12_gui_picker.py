"""GUI adapter: pure path/command contract; window clicks require actual Windows."""
from pathlib import Path
import tempfile
import unittest
from sld_ci_v04_beta3.sap_picker_gui import (
    ENGINE_MODULE, build_export_command, default_plant_id, valid_plant_id,
)


class Alpha12GuiPickerTests(unittest.TestCase):
    def test_default_plant_id_uses_pdf_name(self):
        self.assertEqual(default_plant_id(Path("PV11_Pampa_Norte.pdf")), "PV11_Pampa_Norte")

    def test_name_with_spaces_uses_safe_folder(self):
        self.assertEqual(default_plant_id(Path("Pampa Norte (2026).PDF")), "Pampa_Norte__2026")

    def test_identifiers_cannot_escape_report_folder(self):
        for bad in ("", "../../Pampa", "../PV11", "plant/subfolder", "a\\b", "A B", "A&B"):
            self.assertFalse(valid_plant_id(bad), msg=bad)
        self.assertTrue(valid_plant_id("PV11_Pampa_Norte"))

    def test_pdf_path_with_spaces_and_accents_is_single_argument(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "impianto fotovoltaico à (finale).PDF"
            pdf.write_bytes(b"%PDF-1.4\n")
            output = Path(td) / "rapporti finali"
            cmd = build_export_command(pdf, "PV11_Pampa_Norte", output, executable="python")
            self.assertEqual(cmd[:3], ["python", "-m", ENGINE_MODULE])
            self.assertEqual(cmd[cmd.index("--sld") + 1], str(pdf))
            self.assertEqual(cmd[cmd.index("--out-dir") + 1], str(output))
            self.assertNotIn("--review-json", cmd)

    def test_optional_review_added_only_if_selected(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "file.pdf"
            pdf.touch()
            review = Path(td) / "HITL review.json"
            review.write_text("{}")
            cmd = build_export_command(pdf, "PV11", Path(td) / "results", review, executable="python")
            self.assertEqual(cmd[cmd.index("--review-json") + 1], str(review))

    def test_nonexistent_pdf_rejected_without_running_engine(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                build_export_command(Path(td) / "missing.pdf", "PV11", Path(td) / "out")

    def test_wrong_review_extension_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "plan.pdf"; pdf.touch()
            wrong = Path(td) / "approval.txt"; wrong.touch()
            with self.assertRaises(ValueError):
                build_export_command(pdf, "PV11", Path(td) / "out", wrong)


if __name__ == "__main__":
    unittest.main()
