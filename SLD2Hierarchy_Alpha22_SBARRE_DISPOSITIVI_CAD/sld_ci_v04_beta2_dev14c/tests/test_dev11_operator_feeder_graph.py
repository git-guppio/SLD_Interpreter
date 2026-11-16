import unittest

from sld_ci_v04_beta2_dev14c.operator_interaction import validate_feedback
from sld_ci_v04_beta2_dev14c.operator_learning import patterns_from_feedback
from sld_ci_v04_beta2_dev14c.feeder_operator_patterns import (
    derive_xfr_binding_value,
    derive_bridge_value,
    bind_xfr_terminals,
    apply_conductive_gap_patterns,
)
from sld_ci_v04_beta2_dev14c.feeder_verification import resolve_feeder_verification


class Dev11OperatorFeederGraphTests(unittest.TestCase):
    def test_feeder_feedback_contract_and_learning_is_plant_scoped(self):
        value = derive_xfr_binding_value([10, 10, 30, 20], [20, 60], feeder_id="MV-01", xfr_instance_key="1", page=1)
        fb = validate_feedback({
            "request_id": "P::REQ::1",
            "target": "FEEDER_ELECTRICAL_PATH_VERIFICATION",
            "option": "PROVIDE_VALUE",
            "status": "OPERATOR_PROVIDED",
            "plant_id": "P",
            "learning_scope": "PLANT",
            "value": value,
        })
        pats = patterns_from_feedback([fb])
        self.assertEqual(pats[0]["pattern_type"], "XFR_MV_TERMINAL_BINDING_PATTERN")
        self.assertEqual(pats[0]["scope"], "PLANT")
        self.assertEqual(pats[0]["origin_plant_id"], "P")

    def test_xfr_terminal_offset_binds_repeated_tags(self):
        pages = [{
            "page": 1,
            "planar_graph": {
                "nodes": [
                    {"node_id": 1, "point": [20, 60], "node_type": "ENDPOINT"},
                    {"node_id": 2, "point": [70, 60], "node_type": "ENDPOINT"},
                ],
                "edges": [],
            },
            "text_equipment_anchors": [
                {"evidence_kind": "XFR_TAG", "bbox": [10,10,30,20], "attributes": {"xfr_instance_hint": 1}},
                {"evidence_kind": "XFR_TAG", "bbox": [60,10,80,20], "attributes": {"xfr_instance_hint": 2}},
            ],
        }]
        pat = derive_xfr_binding_value([10,10,30,20], [20,60])
        pat["origin"] = "OPERATOR_PROVIDED"
        out = bind_xfr_terminals(pages, [pat])
        self.assertEqual(out["1"][0]["graph_node_id"], 1)
        self.assertEqual(out["2"][0]["graph_node_id"], 2)

    def test_conductive_gap_pattern_bridges_matching_endpoints(self):
        page = {
            "planar_graph": {
                "nodes": [
                    {"node_id": 1, "point": [10,10], "node_type": "ENDPOINT"},
                    {"node_id": 2, "point": [10,20], "node_type": "ENDPOINT"},
                    {"node_id": 3, "point": [10,30], "node_type": "ENDPOINT"},
                    {"node_id": 4, "point": [10,40], "node_type": "ENDPOINT"},
                ],
                "edges": [
                    {"source": 1, "target": 2},
                    {"source": 3, "target": 4},
                ],
            }
        }
        pat = derive_bridge_value([10,20],[10,30])
        out = apply_conductive_gap_patterns(page, [pat], focus_points=[[10,25]])
        self.assertIn(3, out["adjacency"][2])
        self.assertEqual(len(out["added_bridges"]), 1)

    def test_operator_calibrated_sld_trace_can_verify_schedule_membership(self):
        # Root segment: node 1--2, one conductive gap 2..3, then node 3--4 at XFR terminal.
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
                "evidence_kind": "XFR_TAG", "bbox": [10,10,30,20], "attributes": {"xfr_instance_hint": 1}, "page": 1,
            }],
            "document_semantics": {"has_substation_breaker": True},
        }]
        layout = [{"page": 1, "mv_circuit_schedule_rows": [{
            "block_instance_key": "1", "mv_line_instance_key": "MV-01", "page": 1, "doc": "L"
        }]}]
        xval = derive_xfr_binding_value([10,10,30,20],[20,60],feeder_id="MV-01",xfr_instance_key="1",page=1)
        bval = derive_bridge_value([20,100],[20,90],feeder_id="MV-01",page=1)
        feedback = [
            {"target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":xval},
            {"target":"FEEDER_ELECTRICAL_PATH_VERIFICATION","option":"PROVIDE_VALUE","status":"OPERATOR_PROVIDED","plant_id":"P","value":bval},
        ]
        fv = resolve_feeder_verification(
            sld, layout, plant_id="P", legacy_layout_resolution={"cu_mv_membership": []},
            operator_feedback=feedback, learned_patterns=[]
        )
        self.assertEqual(fv["summary"]["explicit_schedule_membership_count"], 1)
        self.assertEqual(fv["summary"]["operator_xfr_terminal_bound_instance_count"], 1)
        self.assertEqual(fv["summary"]["operator_calibrated_graph_verified_count"], 1)
        self.assertEqual(fv["summary"]["graph_verified_cu_mv_membership_count"], 1)


    def test_feeder_root_pattern_binds_delimited_line_anchor(self):
        from sld_ci_v04_beta2_dev14c.feeder_operator_patterns import derive_feeder_root_value, bind_feeder_roots
        pages=[{
            "page":1,
            "layout_mv_line_anchors":[{"text":"MV_01","line_instance_hint":"MV-01","anchor_role":"INSTANCE","bbox":[10,100,30,110]}],
            "planar_graph":{"nodes":[{"node_id":7,"point":[40,90],"node_type":"ENDPOINT"}],"edges":[]},
        }]
        pat=derive_feeder_root_value([10,100,30,110],[40,90],feeder_id="MV-01",anchor_text="MV_01",page=1)
        pat["origin"]="OPERATOR_PROVIDED"
        out=bind_feeder_roots(pages,[pat])
        self.assertEqual(out["MV-01"][0]["graph_node_id"],7)

    def test_instance_bridge_is_exact_not_learned_pattern(self):
        from sld_ci_v04_beta2_dev14c.feeder_operator_patterns import derive_instance_bridge_value, apply_instance_bridges
        page={"page":2,"planar_graph":{"nodes":[
            {"node_id":1,"point":[10,10],"node_type":"ENDPOINT"},
            {"node_id":2,"point":[10,20],"node_type":"ENDPOINT"}],"edges":[]}}
        rec=derive_instance_bridge_value([10,10],[10,20],feeder_id="MV-01",page=2)
        rec["origin"]="OPERATOR_PROVIDED"
        out=apply_instance_bridges(page,[rec])
        self.assertIn(2,out["adjacency"][1])
        self.assertEqual(len(out["added_bridges"]),1)

    def test_no_operator_patterns_preserves_dev10_behavior(self):
        fv = resolve_feeder_verification([], [], plant_id="P", operator_feedback=[], learned_patterns=[])
        self.assertEqual(fv["summary"]["operator_xfr_terminal_bound_instance_count"], 0)
        self.assertEqual(fv["summary"]["operator_added_bridge_count"], 0)


if __name__ == "__main__":
    unittest.main()

class Dev11eGuiFeedbackTests(unittest.TestCase):
    def test_guided_feedback_identity_distinguishes_root_and_xfr(self):
        from sld_ci_v04_beta2_dev14c.operator_feeder import FeederCalibrationApp, MODE_ROOT, MODE_XFR
        root = {"value":{"action":MODE_ROOT,"feeder_id":"MV-01"}}
        xfr = {"value":{"action":MODE_XFR,"feeder_id":"MV-01","xfr_instance_key":"1"}}
        self.assertNotEqual(FeederCalibrationApp._feedback_identity(root), FeederCalibrationApp._feedback_identity(xfr))
        self.assertEqual(FeederCalibrationApp._feedback_identity(root), (MODE_ROOT,"MV-01"))
        self.assertEqual(FeederCalibrationApp._feedback_identity(xfr), (MODE_XFR,"MV-01","1"))
