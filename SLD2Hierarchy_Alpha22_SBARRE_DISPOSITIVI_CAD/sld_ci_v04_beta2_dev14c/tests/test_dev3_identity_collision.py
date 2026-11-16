import unittest
from sld_ci_v04_beta2_dev14c.target_entity_resolution import resolve_target_entities


class Dev3IdentityCollisionTests(unittest.TestCase):
    def test_duplicate_tag_conflicting_with_page_cu_is_diagnostic(self):
        pages = [
            {"doc": "D", "page": 1, "text_equipment_anchors": [
                {"anchor_id": "CU1", "doc": "D", "page": 1, "equipment_type": "CONVERSION_UNIT", "anchor_role": "INSTANCE", "attributes": {"instance_hint": 1}},
                {"anchor_id": "SB1", "doc": "D", "page": 1, "equipment_type": "STRING_BOX", "anchor_role": "TAG", "tag": "CST-01", "text": "CST-01", "attributes": {"cu_instance_hint": 1}},
            ]},
            {"doc": "D", "page": 2, "text_equipment_anchors": [
                {"anchor_id": "CU7", "doc": "D", "page": 2, "equipment_type": "CONVERSION_UNIT", "anchor_role": "INSTANCE", "attributes": {"instance_hint": 7}},
                {"anchor_id": "SB2", "doc": "D", "page": 2, "equipment_type": "STRING_BOX", "anchor_role": "TAG", "tag": "CST-01", "text": "CST-01", "attributes": {"cu_instance_hint": 1}},
            ]},
        ]
        out = resolve_target_entities(pages, [])
        self.assertEqual(out["raw_source_instance_counts"]["STRING_BOX"], 2)
        self.assertEqual(out["counts"]["STRING_BOX"], 1)
        self.assertFalse(out["identity_resolution_complete"])
        self.assertEqual(out["source_instance_collisions"][0]["status"], "POSSIBLE_MISTAG_OR_DUPLICATE_INSTANCE")


if __name__ == "__main__":
    unittest.main()
