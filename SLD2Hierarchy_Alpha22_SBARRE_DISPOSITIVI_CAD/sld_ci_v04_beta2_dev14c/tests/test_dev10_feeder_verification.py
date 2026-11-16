import unittest

from sld_ci_v04_beta2_dev14c.models import TextItem
from sld_ci_v04_beta2_dev14c.schedule_evidence import extract_mv_circuit_schedule_rows
from sld_ci_v04_beta2_dev14c.source_resolution import resolve_page_role
from sld_ci_v04_beta2_dev14c.feeder_verification import (
    resolve_feeder_verification,
    apply_feeder_membership_to_layout_resolution,
)


class Dev10FeederVerificationTests(unittest.TestCase):
    def _items(self):
        # title y=20, headers y~50, row baseline y=90
        return [
            TextItem("MV-03 CIRCUIT SCHEDULE", (10, 10, 150, 30), 1, "D"),
            TextItem("BLOCK #", (10, 45, 55, 60), 1, "D"),
            TextItem("21", (15, 85, 30, 95), 1, "D"),
            TextItem("8100N", (55, 85, 95, 95), 1, "D"),
            TextItem("15", (118, 85, 132, 95), 1, "D"),
            TextItem("TRINA", (175, 85, 215, 95), 1, "D"),
            TextItem("E-209", (245, 85, 285, 95), 1, "D"),
        ]

    def test_explicit_mv_circuit_schedule_parses_membership(self):
        rows = extract_mv_circuit_schedule_rows(self._items())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mv_line_instance_key"], "MV-03")
        self.assertEqual(rows[0]["block_instance_key"], "21")
        self.assertEqual(rows[0]["evidence_kind"], "EXPLICIT_MV_CIRCUIT_SCHEDULE_MEMBERSHIP")

    def test_layout_page_role_mv_circuit_schedule(self):
        page = {
            "page_type": "SCHEDULE",
            "mv_circuit_schedule_rows": [{"block_instance_key": "21", "mv_line_instance_key": "MV-03"}],
        }
        r = resolve_page_role(page, "LAYOUT")
        self.assertEqual(r["page_role"], "MV_CIRCUIT_SCHEDULE")

    def test_schedule_resolves_membership_without_claiming_graph_verification(self):
        layout_pages = [{
            "page": 8,
            "mv_circuit_schedule_rows": [{
                "block_instance_key": "21",
                "mv_line_instance_key": "MV-03",
                "page": 8,
                "doc": "L",
            }],
        }]
        sld_pages = [{
            "page": 2,
            "page_role": "ELECTRICAL_SLD",
            "text_equipment_anchors": [{
                "evidence_kind": "XFR_TAG",
                "attributes": {"xfr_instance_hint": 21},
                "tag": "XFR_21",
                "bbox": [10, 10, 20, 20],
                "page": 2,
            }],
            "layout_mv_line_anchors": [],
            "planar_graph": {"nodes": [], "edges": []},
            "document_semantics": {"has_project_substation": True},
        }]
        fv = resolve_feeder_verification(
            sld_pages, layout_pages,
            template_schedule_resolution={"semantic_support": {}, "inferred_target_counts": {}},
            legacy_layout_resolution={"cu_mv_membership": []},
            plant_id="CI::T",
        )
        self.assertEqual(fv["summary"]["explicit_schedule_membership_count"], 1)
        self.assertEqual(fv["summary"]["graph_verified_cu_mv_membership_count"], 0)
        self.assertEqual(fv["summary"]["sld_xfr_identity_crosschecked_count"], 1)
        self.assertEqual(len(fv["resolution_requests"]), 1)
        self.assertEqual(fv["resolution_requests"][0]["required_for"], "TOPOLOGY_VERIFICATION_NOT_MEMBERSHIP_COUNT")

        lr = {
            "mv_lines": [{"instance_key": "MV-03", "label_status": "RESOLVED"}],
            "cu_mv_membership": [],
            "unresolved_membership": [{"cu_instance_key": "21"}],
            "summary": {},
        }
        out = apply_feeder_membership_to_layout_resolution(lr, fv)
        self.assertEqual(out["summary"]["resolved_cu_mv_membership_count"], 1)
        self.assertFalse(out["cu_mv_membership"][0]["topology_verified"])
        self.assertEqual(out["cu_mv_membership"][0]["membership_source"], "EXPLICIT_SOURCE_SCHEDULE")
        self.assertEqual(out["unresolved_membership"], [])

    def test_no_schedule_preserves_legacy_membership(self):
        legacy = {
            "mv_lines": [{"instance_key": "L1"}],
            "cu_mv_membership": [{"cu_instance_key": "1", "mv_line_instance_key": "L1", "basis": "LEGACY"}],
            "unresolved_membership": [],
            "summary": {"resolved_cu_mv_membership_count": 1},
        }
        fv = resolve_feeder_verification([], [], legacy_layout_resolution=legacy, plant_id="CI::P")
        out = apply_feeder_membership_to_layout_resolution(legacy, fv)
        self.assertEqual(out["cu_mv_membership"][0]["basis"], "LEGACY")
        self.assertEqual(out["summary"]["resolved_cu_mv_membership_count"], 1)


if __name__ == "__main__":
    unittest.main()
