import unittest

from sld_ci_v04_beta2_dev14c.layout_resolution import (
    build_layout_resolution_requests,
    resolve_layout,
)
from sld_ci_v04_beta2_dev14c.operator_interaction import validate_feedback
from sld_ci_v04_beta2_dev14c.operator_learning import patterns_from_feedback
from sld_ci_v04_beta2_dev14c.operator_layout import build_feedback


def _page():
    feeders = []
    for i, x in enumerate((100, 300, 500), 1):
        feeders.append({
            "candidate_id": f"F{i}",
            "synthetic_line_key": f"LAYOUT_FEEDER_{i:02d}",
            "bbox": [x-15, 125, x+15, 140],
            "trunk": {"x": x},
            "label_status": "UNRESOLVED",
            "raw_header_text": f"@@{i}",
        })
    anchors = []
    for n, x in enumerate((112, 118, 312, 318, 512, 518), 1):
        anchors.append({
            "equipment_type": "CONVERSION_UNIT",
            "anchor_role": "INSTANCE",
            "anchor_id": f"CU{n}",
            "text": f"CABINA {n}",
            "bbox": [x-5, 400, x+5, 410],
            "attributes": {"instance_hint": n},
        })
    return {
        "page": 1,
        "doc": "CI::T::LAYOUT",
        "page_width_pt": 1000,
        "page_height_pt": 1000,
        "text_equipment_anchors": anchors,
        "layout_mv_line_anchors": [],
        "layout_feeder_candidates": feeders,
        "planar_graph": {"nodes": [], "edges": []},
    }


class Dev8MVLineOperatorMappingTests(unittest.TestCase):
    def test_unresolved_feeders_create_one_grouped_mapping_request(self):
        r = resolve_layout([_page()], plant_id="CI::T")
        req = build_layout_resolution_requests(r, plant_id="CI::T")
        self.assertEqual(len(req), 1)
        self.assertEqual(req[0]["target"], "MV_LINE_LABEL_MAPPING")
        self.assertEqual(req[0]["context"]["mapping_keys"], [
            "LAYOUT_FEEDER_01", "LAYOUT_FEEDER_02", "LAYOUT_FEEDER_03"
        ])

    def test_operator_mapping_resolves_labels_without_changing_membership_topology(self):
        fb = validate_feedback({
            "request_id": "CI::T::REQ::MV_LINE_LABEL_MAPPING",
            "target": "MV_LINE_LABEL_MAPPING",
            "option": "PROVIDE_VALUE",
            "value": {
                "LAYOUT_FEEDER_01": "LINEA 1",
                "LAYOUT_FEEDER_02": "LINEA 2",
                "LAYOUT_FEEDER_03": "LINEA 3",
            },
            "status": "OPERATOR_PROVIDED",
            "plant_id": "CI::T",
        })
        r = resolve_layout([_page()], plant_id="CI::T", operator_feedback=[fb])
        self.assertEqual(r["summary"]["unresolved_mv_line_label_count"], 0)
        self.assertEqual(r["summary"]["operator_or_learned_mv_line_label_count"], 3)
        self.assertEqual({m["mv_line_instance_key"] for m in r["cu_mv_membership"]}, {
            "LINEA 1", "LINEA 2", "LINEA 3"
        })
        self.assertTrue(all(m["source_status"] == "INFERRED" for m in r["cu_mv_membership"]))
        self.assertTrue(all(m["line_label_source_status"] == "OPERATOR_PROVIDED" for m in r["cu_mv_membership"]))

    def test_plant_scoped_learned_mapping_reuses_only_on_same_plant(self):
        fb = {
            "request_id": "CI::T::REQ::MV_LINE_LABEL_MAPPING",
            "target": "MV_LINE_LABEL_MAPPING",
            "option": "PROVIDE_VALUE",
            "value": {
                "LAYOUT_FEEDER_01": "L1",
                "LAYOUT_FEEDER_02": "L2",
                "LAYOUT_FEEDER_03": "L3",
            },
            "status": "OPERATOR_PROVIDED",
            "plant_id": "CI::T",
            "learning_scope": "PLANT",
        }
        patterns = patterns_from_feedback([fb])
        same = resolve_layout([_page()], plant_id="CI::T", learned_patterns=patterns)
        other = resolve_layout([_page()], plant_id="CI::OTHER", learned_patterns=patterns)
        self.assertEqual(same["summary"]["unresolved_mv_line_label_count"], 0)
        self.assertEqual(other["summary"]["unresolved_mv_line_label_count"], 3)

    def test_console_feedback_builder_preserves_operator_provenance(self):
        r = resolve_layout([_page()], plant_id="CI::T")
        analysis = {
            "plant": {"plant_id": "CI::T"},
            "sources": {"layout": {"doc_id": "CI::T::LAYOUT", "file_name": "T_LAYOUT.pdf"}},
            "layout_resolution": r,
            "layout_resolution_requests": build_layout_resolution_requests(r, plant_id="CI::T"),
        }
        fb = build_feedback(analysis, ["LINEA A", "LINEA B", "LINEA C"])
        self.assertEqual(fb["status"], "OPERATOR_PROVIDED")
        self.assertEqual(fb["learning_scope"], "PLANT")
        self.assertEqual(fb["value"]["LAYOUT_FEEDER_02"], "LINEA B")


if __name__ == "__main__":
    unittest.main()
