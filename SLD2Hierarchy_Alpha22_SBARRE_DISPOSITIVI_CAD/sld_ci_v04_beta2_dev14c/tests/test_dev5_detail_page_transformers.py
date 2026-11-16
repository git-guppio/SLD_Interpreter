import unittest

from sld_ci_v04_beta2_dev14c.models import TextItem
from sld_ci_v04_beta2_dev14c.text_detection import detect_text_equipment_anchors
from sld_ci_v04_beta2_dev14c.detail_page_resolution import resolve_detail_page_transformers
from sld_ci_v04_beta2_dev14c.target_hierarchy import build_target_hierarchy


class Dev5DetailPageTransformerTests(unittest.TestCase):
    def _anchors(self, texts):
        items = [TextItem(text=t, bbox=b, page=2, doc="CI::TEST") for t, b in texts]
        return [a.__dict__ for a in detect_text_equipment_anchors(items)]

    def test_cross_sheet_subcampo_reference_is_not_instance(self):
        anchors = self._anchors([
            ("A SUBCAMPO 4", (10, 10, 80, 20)),
            ("DE SUBCAMPO 2", (10, 30, 80, 40)),
            ("Subcampo 1. (2,92144MW)", (100, 10, 220, 20)),
        ])
        refs = [a for a in anchors if a["equipment_type"] == "CONVERSION_UNIT" and a["anchor_role"] == "REFERENCE"]
        inst = [a for a in anchors if a["equipment_type"] == "CONVERSION_UNIT" and a["anchor_role"] == "INSTANCE"]
        self.assertEqual({a["attributes"]["instance_hint"] for a in refs}, {2, 4})
        self.assertEqual({a["attributes"]["instance_hint"] for a in inst}, {1})

    def test_voltage_ratio_parses_036_to_33kv(self):
        anchors = self._anchors([("0,36/33KV", (100, 100, 150, 110))])
        ratio = next(a for a in anchors if a.get("evidence_kind") == "VOLTAGE_RATIO")
        self.assertEqual(ratio["attributes"]["voltage_values_v"], [360.0, 33000.0])

    def test_two_local_rating_ratio_clusters_infer_two_mv_lv_transformers(self):
        anchors = self._anchors([
            ("Subcampo 1. (2,92144MW)", (100, 20, 250, 30)),
            ("1600 kVA", (100, 100, 150, 110)),
            ("0,36/33KV", (100, 116, 155, 126)),
            ("1600 kVA", (300, 100, 350, 110)),
            ("0,36/33KV", (300, 116, 355, 126)),
        ])
        page = {
            "doc": "CI::TEST", "page": 2,
            "page_width_pt": 600, "page_height_pt": 800,
            "text_equipment_anchors": anchors,
        }
        r = resolve_detail_page_transformers([page], [])
        self.assertEqual(r["summary"]["mv_lv_transformer_count"], 2)
        self.assertEqual(r["summary"]["unresolved_cluster_count"], 0)
        self.assertTrue(all(e["source_status"] == "INFERRED" for e in r["entities"]))
        self.assertTrue(all(e["cu_instance_hint"] == "1" for e in r["entities"]))

    def test_inferred_transformers_attach_to_resolved_cu(self):
        anchors = self._anchors([
            ("Subcampo 1. (2,92144MW)", (100, 20, 250, 30)),
            ("1600 kVA", (100, 100, 150, 110)),
            ("0,36/33KV", (100, 116, 155, 126)),
            ("1600 kVA", (300, 100, 350, 110)),
            ("0,36/33KV", (300, 116, 355, 126)),
        ])
        page = {
            "doc": "CI::TEST", "page": 2,
            "page_width_pt": 600, "page_height_pt": 800,
            "text_equipment_anchors": anchors,
        }
        r = resolve_detail_page_transformers([page], [])
        containers = {"entities": [{
            "entity_id": "CI::TEST::CU::1", "entity_type": "CONVERSION_UNIT",
            "doc": "CI::TEST", "instance_key": "1", "canonical_label": "SUBCAMPO 1",
            "source_status": "DETECTED",
        }]}
        h = build_target_hierarchy([page], containers, r["entities"])
        self.assertEqual(h["conversion_units"][0]["mv_lv_transformer_count"], 2)
        self.assertEqual(h["unresolved_membership"], [])


if __name__ == "__main__":
    unittest.main()
