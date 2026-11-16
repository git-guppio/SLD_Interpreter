import unittest

from sld_ci_v04_beta2_dev14c.ingestion import classify_page_lightweight
from sld_ci_v04_beta2_dev14c.layout_evidence import detect_mv_line_anchors
from sld_ci_v04_beta2_dev14c.models import TextItem
from sld_ci_v04_beta2_dev14c.schedule_evidence import extract_block_schedule_rows
from sld_ci_v04_beta2_dev14c.template_schedule_resolution import resolve_template_schedule_model


class Dev9TemplateScheduleGeneralizationTests(unittest.TestCase):
    def test_single_line_title_outranks_embedded_schedule(self):
        items = [
            TextItem("CIRCUIT SCHEDULE", (0, 0, 10, 10), 1, "D"),
            TextItem("INVERTER DC SINGLE LINE DIAGRAM", (0, 20, 100, 30), 1, "D"),
        ]
        typ, reasons = classify_page_lightweight(items)
        self.assertEqual(typ, "SLD")
        self.assertTrue(any("single-line" in x for x in reasons))

    def test_standalone_mv_ids_emit_all_identifiers_in_same_text_span(self):
        items = [TextItem("MV-01 MV_02 MV-16", (0, 0, 100, 10), 1, "D")]
        out = detect_mv_line_anchors(items, 1, "D")
        self.assertEqual([x["line_instance_hint"] for x in out], ["MV-01", "MV-02", "MV-16"])

    def test_positioned_block_schedule_requires_aligned_columns(self):
        items = [
            TextItem("BLOCK SCHEDULE", (100, 0, 200, 10), 1, "D"),
            TextItem("BLOCK #", (100, 20, 140, 30), 1, "D"),
            TextItem("1", (110, 50, 120, 60), 1, "D"),
            TextItem("8100A", (150, 50, 190, 60), 1, "D"),
            TextItem("15", (220, 50, 235, 60), 1, "D"),
            TextItem("TRINA", (275, 50, 315, 60), 1, "D"),
            TextItem("E-204", (340, 50, 380, 60), 1, "D"),
        ]
        rows = extract_block_schedule_rows(items)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["block_instance_key"], "1")
        self.assertEqual(rows[0]["combiner_box_count"], 15)

    def test_document_local_alignment_expands_template_without_global_alias(self):
        sld_doc = "CI::T::SLD"
        layout_doc = "CI::T::LAYOUT"
        sld_pages = [{
            "page": 1,
            "doc": sld_doc,
            "page_role": "ELECTRICAL_SLD",
            "document_semantics": {
                "has_skid_family": True,
                "has_intermediate_step_up_transformer": True,
                "has_from_inverter": True,
                "typical_skid_counts": [2],
                "typical_skid_evidence": [{"page": 1, "bbox": [0, 0, 10, 10], "text": "INVERTER TYPICAL FOR 2 SKIDS"}],
            },
            "text_equipment_anchors": [
                {"anchor_id": "x1", "page": 1, "doc": sld_doc, "bbox": [0, 0, 1, 1], "text": "XFR_1", "evidence_kind": "XFR_TAG", "attributes": {"xfr_instance_hint": 1}},
                {"anchor_id": "x2", "page": 1, "doc": sld_doc, "bbox": [1, 0, 2, 1], "text": "XFR_2", "evidence_kind": "XFR_TAG", "attributes": {"xfr_instance_hint": 2}},
            ],
        }]
        layout_pages = [{
            "page": 1,
            "doc": layout_doc,
            "page_role": "CONTAINER_SCHEDULE",
            "document_semantics": {"has_power_block_family": True, "typical_skid_counts": []},
            "block_schedule_rows": [
                {"block_instance_key": "1", "combiner_box_count": 14, "wiring_pattern": "A1", "module_manufacturer": "M", "detail_sheet": "E-1", "page": 1, "bbox": [0, 0, 1, 1]},
                {"block_instance_key": "2", "combiner_box_count": 15, "wiring_pattern": "A2", "module_manufacturer": "M", "detail_sheet": "E-2", "page": 1, "bbox": [1, 0, 2, 1]},
            ],
            "text_equipment_anchors": [],
        }]
        r = resolve_template_schedule_model(sld_pages, layout_pages, plant_id="CI::T")
        self.assertEqual(r["status"], "RESOLVED")
        self.assertEqual(len(r["container_entities"]), 2)
        self.assertEqual(r["inferred_target_counts"]["MV_LV_TRANSFORMER"], 2)
        self.assertEqual(r["inferred_target_counts"]["CENTRAL_INVERTER"], 2)
        self.assertEqual(r["inferred_target_counts"]["STRING_BOX"], 29)
        self.assertIn("NO_GLOBAL_POWER_BLOCK_OR_XFR_ALIAS", r["policy"])


if __name__ == "__main__":
    unittest.main()
