import unittest

from sld_ci_v04_beta2_dev14c.source_resolution import (
    normalized_case_key,
    resolve_page_role,
    validate_source_pair,
)
from sld_ci_v04_beta2_dev14c.source_reconciliation import reconcile_sources
from sld_ci_v04_beta2_dev14c.layout_resolution import resolve_layout


class Dev6MultiSourceTests(unittest.TestCase):
    def test_sld_and_layout_filename_pair_resolve_same_plant(self):
        self.assertEqual(normalized_case_key("PV8_SLD.pdf"), "PV8")
        self.assertEqual(normalized_case_key("PV8_LAYOUT.pdf"), "PV8")
        r = validate_source_pair("PV8_SLD.pdf", "PV8_LAYOUT.pdf")
        self.assertEqual(r["plant_id"], "CI::PV8")
        self.assertTrue(r["source_name_consistent"])

    def test_layout_page_role_does_not_depend_on_page_number(self):
        page = {"page": 7, "page_type": "OTHER", "text_equipment_anchors": []}
        r = resolve_page_role(page, "LAYOUT")
        self.assertEqual(r["page_role"], "PLANT_LAYOUT_OVERVIEW")
        self.assertEqual(r["basis"], "EXPLICIT_SOURCE_DOCUMENT_ROLE")

    def test_sld_detail_page_role_from_unique_local_cu(self):
        page = {
            "page": 12,
            "page_type": "OTHER",
            "text_equipment_anchors": [{
                "equipment_type": "CONVERSION_UNIT",
                "anchor_role": "INSTANCE",
                "attributes": {"instance_hint": 26},
            }],
        }
        r = resolve_page_role(page, "SLD")
        self.assertEqual(r["page_role"], "CU_DETAIL")
        self.assertEqual(r["cu_instance_hint"], "26")

    def test_reconciliation_unions_cu_identity_without_duplicate_assets(self):
        sld = {"entities": [
            {"entity_id": "CI::PV8::SLD::CU::1", "instance_key": "1", "source_status": "DETECTED", "representations": []},
            {"entity_id": "CI::PV8::SLD::CU::2", "instance_key": "2", "source_status": "DETECTED", "representations": []},
        ]}
        layout = {
            "mv_lines": [],
            "cu_mv_membership": [],
            "unresolved_membership": [],
            "conversion_unit_representations": [
                {"cu_instance_key": "1", "page": 1},
                {"cu_instance_key": "2", "page": 1},
                {"cu_instance_key": "3", "page": 1},
            ],
        }
        r = reconcile_sources("CI::PV8", sld, layout)
        self.assertEqual(r["summary"]["canonical_conversion_unit_count"], 3)
        self.assertEqual(r["summary"]["matched_across_sources"], 2)
        self.assertEqual(r["summary"]["layout_only"], 1)

    def test_layout_membership_requires_explicit_line_id_and_shared_component(self):
        # One connected component; line and CU labels are both close to it.
        page = {
            "page": 1,
            "doc": "CI::TEST::LAYOUT",
            "page_width_pt": 1000,
            "page_height_pt": 1000,
            "text_equipment_anchors": [{
                "equipment_type": "CONVERSION_UNIT",
                "anchor_role": "INSTANCE",
                "anchor_id": "CU1",
                "text": "CABINA 1",
                "bbox": [95, 95, 105, 105],
                "attributes": {"instance_hint": 1},
            }],
            "layout_mv_line_anchors": [{
                "equipment_type": "MV_LINE",
                "anchor_role": "INSTANCE",
                "anchor_id": "L1",
                "text": "LINEA MT 1",
                "bbox": [195, 95, 205, 105],
                "line_instance_hint": "1",
            }],
            "planar_graph": {
                "nodes": [
                    {"node_id": 1, "point": [100, 100]},
                    {"node_id": 2, "point": [200, 100]},
                ],
                "edges": [{"source": 1, "target": 2}],
            },
        }
        r = resolve_layout([page])
        self.assertEqual(r["summary"]["mv_line_count"], 1)
        self.assertEqual(r["summary"]["resolved_cu_mv_membership_count"], 1)
        self.assertEqual(r["cu_mv_membership"][0]["mv_line_instance_key"], "1")
        self.assertEqual(r["cu_mv_membership"][0]["basis"], "EXPLICIT_LINE_ID_PLUS_SHARED_GRAPH_COMPONENT")

    def test_layout_without_line_id_does_not_guess_membership(self):
        page = {
            "page": 1,
            "doc": "CI::TEST::LAYOUT",
            "page_width_pt": 1000,
            "page_height_pt": 1000,
            "text_equipment_anchors": [{
                "equipment_type": "CONVERSION_UNIT",
                "anchor_role": "INSTANCE",
                "anchor_id": "CU1",
                "text": "CABINA 1",
                "bbox": [95, 95, 105, 105],
                "attributes": {"instance_hint": 1},
            }],
            "layout_mv_line_anchors": [],
            "planar_graph": {
                "nodes": [{"node_id": 1, "point": [100, 100]}],
                "edges": [],
            },
        }
        r = resolve_layout([page])
        self.assertEqual(r["cu_mv_membership"], [])
        self.assertTrue(r["unresolved_membership"])


if __name__ == "__main__":
    unittest.main()
