import unittest

from sld_ci_v04_beta2_dev14c.target_summary import summarize_target_hierarchy
from sld_ci_v04_beta2_dev14c.resolution_engine import build_resolution_requests


class Dev4TargetCountsAndRatingResolutionTests(unittest.TestCase):
    def test_target_counts_come_from_resolved_hierarchy(self):
        h = {
            "conversion_units": [
                {
                    "iocb_count": 1, "mv_lv_transformer_count": 2,
                    "inverters": [
                        {"lv_lv_transformer_count": 1, "string_box_count": 6},
                        {"lv_lv_transformer_count": 0, "string_box_count": 5},
                    ],
                }
            ],
            "unresolved_membership": [{"x": 1}],
        }
        s = summarize_target_hierarchy(h)
        self.assertEqual(s["conversion_units"], 1)
        self.assertEqual(s["mv_lv_transformers"], 2)
        self.assertEqual(s["inverters"], 2)
        self.assertEqual(s["string_boxes"], 11)
        self.assertEqual(s["lv_lv_transformers"], 1)
        self.assertEqual(s["unresolved_membership"], 1)

    def test_power_rating_without_resolved_transformer_creates_visual_request(self):
        pages = [{
            "doc": "CI::TEST", "page": 2,
            "text_equipment_anchors": [{
                "anchor_id": "A1", "doc": "CI::TEST", "page": 2,
                "equipment_type": "TRANSFORMER_CANDIDATE",
                "anchor_role": "RATING",
                "evidence_kind": "APPARENT_POWER_RATING",
                "text": "1600 kVA", "bbox": [10, 20, 40, 30],
                "attributes": {"apparent_power_kva": 1600.0},
            }],
        }]
        reqs = build_resolution_requests(
            pages, [], [], container_resolution={"entities": []},
            target_hierarchy={"conversion_units": []},
        )
        hits = [r for r in reqs if r["reason"] == "APPARENT_POWER_RATING_EVIDENCE_WITHOUT_RESOLVED_TRANSFORMER"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["interaction_mode"], "VISUAL_SELECT")
        self.assertEqual(hits[0]["context"]["visual_hints"][0]["rating_text"], "1600 kVA")

    def test_power_rating_does_not_request_when_transformer_is_resolved(self):
        pages = [{
            "doc": "CI::TEST", "page": 2,
            "text_equipment_anchors": [{
                "anchor_id": "A1", "doc": "CI::TEST", "page": 2,
                "equipment_type": "TRANSFORMER_CANDIDATE",
                "anchor_role": "RATING",
                "evidence_kind": "APPARENT_POWER_RATING",
                "text": "1600 kVA", "bbox": [10, 20, 40, 30],
                "attributes": {"apparent_power_kva": 1600.0},
            }],
        }]
        th = {"conversion_units": [{"mv_lv_transformer_count": 1, "inverters": []}]}
        reqs = build_resolution_requests(
            pages, [], [], container_resolution={"entities": []}, target_hierarchy=th
        )
        self.assertFalse(any(r["reason"] == "APPARENT_POWER_RATING_EVIDENCE_WITHOUT_RESOLVED_TRANSFORMER" for r in reqs))


if __name__ == "__main__":
    unittest.main()
