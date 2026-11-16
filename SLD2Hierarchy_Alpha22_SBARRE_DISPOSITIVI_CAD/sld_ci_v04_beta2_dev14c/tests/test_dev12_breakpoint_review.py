import unittest

from sld_ci_v04_beta2_dev14c.operator_interaction import validate_feedback
from sld_ci_v04_beta2_dev14c.feeder_operator_patterns import (
    derive_xfr_binding_value,
    derive_feeder_root_value,
    derive_breakpoint_review_value,
)
from sld_ci_v04_beta2_dev14c.feeder_verification import resolve_feeder_verification


class Dev12BreakpointReviewTests(unittest.TestCase):
    def _sources(self):
        sld = [{
            "page": 1,
            "page_role": "ELECTRICAL_SLD",
            "page_width_pt": 200,
            "page_height_pt": 200,
            "planar_graph": {
                "nodes": [
                    {"node_id": 1, "point": [20,150], "node_type": "ENDPOINT"},
                    {"node_id": 2, "point": [20,100], "node_type": "ENDPOINT"},
                    {"node_id": 3, "point": [20,90], "node_type": "ENDPOINT"},
                    {"node_id": 4, "point": [20,60], "node_type": "ENDPOINT"},
                ],
                "edges": [
                    {"source": 1, "target": 2},
                    {"source": 3, "target": 4},
                ],
            },
            "layout_mv_line_anchors": [{
                "text": "MV_01", "line_instance_hint": "MV-01", "anchor_role": "INSTANCE",
                "bbox": [15,145,25,155], "page": 1,
            }],
            "text_equipment_anchors": [{
                "evidence_kind": "XFR_TAG", "bbox": [10,10,30,20],
                "attributes": {"xfr_instance_hint": 1}, "page": 1,
            }],
            "document_semantics": {"has_substation_breaker": True},
        }]
        layout = [{"page": 1, "mv_circuit_schedule_rows": [{
            "block_instance_key": "1", "mv_line_instance_key": "MV-01", "page": 1, "doc": "L"
        }]}]
        return sld, layout

    def _base_feedback(self):
        xval = derive_xfr_binding_value([10,10,30,20], [20,60], feeder_id="MV-01", xfr_instance_key="1", page=1)
        rval = derive_feeder_root_value([15,145,25,155], [20,150], feeder_id="MV-01", anchor_text="MV_01", page=1)
        return [
            {"target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":xval},
            {"target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":rval},
        ]

    def test_breakpoint_feedback_contract_accepts_device(self):
        value = derive_breakpoint_review_value({
            "feeder_id":"MV-01", "page":1, "source_node_id":2, "target_node_id":3,
            "point_a":[20,100], "point_b":[20,90], "alignment":"V", "distance_pt":10,
        }, classification="INTERPOSED_DEVICE", device_type="SECTIONALIZING_CABINET")
        fb = validate_feedback({
            "request_id":"P::REQ::BP1", "target":"FEEDER_ELECTRICAL_PATH_VERIFICATION",
            "option":"PROVIDE_VALUE", "status":"OPERATOR_PROVIDED", "plant_id":"P", "value":value,
        })
        self.assertEqual(fb["value"]["classification"], "INTERPOSED_DEVICE")
        self.assertEqual(fb["value"]["device_connectivity_state"], "UNKNOWN")

    def test_interposed_device_is_modeled_as_topology_edge_not_conductive_bridge(self):
        sld, layout = self._sources()
        base = self._base_feedback()
        first = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=base, learned_patterns=[])
        bp = first["feeder_traces"][0]["suggested_breakpoints"][0]
        dval = derive_breakpoint_review_value(bp, classification="INTERPOSED_DEVICE", device_type="SECTIONALIZING_CABINET")
        feedback = base + [{
            "target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":dval,
        }]
        out = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=feedback, learned_patterns=[])
        self.assertEqual(out["summary"]["graph_verified_cu_mv_membership_count"], 1)
        self.assertEqual(out["summary"]["breakpoint_interposed_device_count"], 1)
        self.assertEqual(out["summary"]["suggested_breakpoint_count"], 0)
        self.assertEqual(out["operator_graph_calibration"]["added_instance_bridge_count"], 0)
        self.assertEqual(out["operator_graph_calibration"]["added_device_topology_edge_count"], 1)
        self.assertEqual(out["operator_graph_calibration"]["modeled_interposed_device_count"], 1)
        gv = out["graph_verified_membership"][0]
        self.assertEqual(gv["basis"], "OPERATOR_CALIBRATED_SLD_STRUCTURAL_TOPOLOGY_TRACE")

    def test_confirmed_continuity_creates_exact_bridge_and_verifies_path(self):
        sld, layout = self._sources()
        base = self._base_feedback()
        first = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=base, learned_patterns=[])
        bp = first["feeder_traces"][0]["suggested_breakpoints"][0]
        cval = derive_breakpoint_review_value(bp, classification="CONDUCTIVE_CONTINUITY")
        feedback = base + [{
            "target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":cval,
        }]
        out = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=feedback, learned_patterns=[])
        self.assertEqual(out["summary"]["graph_verified_cu_mv_membership_count"], 1)
        self.assertEqual(out["summary"]["breakpoint_continuity_confirmed_count"], 1)
        self.assertGreaterEqual(out["operator_graph_calibration"]["added_instance_bridge_count"], 1)

    def test_undetermined_interposed_device_still_models_structural_topology(self):
        sld, layout = self._sources()
        base = self._base_feedback()
        first = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=base, learned_patterns=[])
        bp = first["feeder_traces"][0]["suggested_breakpoints"][0]
        dval = derive_breakpoint_review_value(bp, classification="INTERPOSED_DEVICE", device_type="UNDETERMINED")
        feedback = base + [{
            "target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":dval,
        }]
        out = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=feedback, learned_patterns=[])
        self.assertEqual(out["summary"]["graph_verified_cu_mv_membership_count"], 1)
        dev = out["operator_graph_calibration"]["interposed_devices"][0]
        self.assertEqual(dev["device_type"], "UNDETERMINED")
        self.assertEqual(dev["device_connectivity_state"], "UNKNOWN")
        self.assertEqual(out["operator_graph_calibration"]["added_bridge_count"], 0)


    def test_non_electrical_graphic_is_excluded_not_bridged(self):
        sld, layout = self._sources()
        base = self._base_feedback()
        first = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=base, learned_patterns=[])
        bp = first["feeder_traces"][0]["suggested_breakpoints"][0]
        gval = derive_breakpoint_review_value(bp, classification="NON_ELECTRICAL_GRAPHIC")
        feedback = base + [{
            "target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":gval,
        }]
        out = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=feedback, learned_patterns=[])
        self.assertEqual(out["summary"]["graph_verified_cu_mv_membership_count"], 0)
        self.assertEqual(out["summary"]["breakpoint_non_electrical_graphic_count"], 1)
        self.assertEqual(out["summary"]["excluded_non_electrical_graphic_node_count"], 2)
        self.assertEqual(out["operator_graph_calibration"]["added_bridge_count"], 0)
        self.assertEqual(out["operator_graph_calibration"]["added_device_topology_edge_count"], 0)
        self.assertEqual(gval["topology_policy"], "EXCLUDE_FROM_FEEDER_TRACE__DO_NOT_BRIDGE")

    def test_without_device_review_dev12_behavior_is_preserved(self):
        sld, layout = self._sources()
        out = resolve_feeder_verification(sld, layout, plant_id="P", operator_feedback=self._base_feedback(), learned_patterns=[])
        self.assertEqual(out["summary"]["graph_verified_cu_mv_membership_count"], 0)
        self.assertEqual(out["operator_graph_calibration"]["added_device_topology_edge_count"], 0)


if __name__ == "__main__":
    unittest.main()
