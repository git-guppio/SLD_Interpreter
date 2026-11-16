import unittest

from sld_ci_v04_beta2_dev14c.layout_feeder_recovery import recover_layout_feeder_candidates
from sld_ci_v04_beta2_dev14c.layout_resolution import resolve_layout
from sld_ci_v04_beta2_dev14c.models import VectorSegment


class _Rect:
    width = 1000.0
    height = 1000.0


class _FakePage:
    rect = _Rect()
    def get_text(self, mode):
        self._mode = mode
        return {
            "blocks": [{"lines": [{"spans": [
                {"text": "@@A", "bbox": [85, 125, 115, 140]},
                {"text": "@@B", "bbox": [285, 125, 315, 140]},
                {"text": "@@C", "bbox": [485, 125, 515, 140]},
            ]}]}]
        }


def _v(seg_id, x, y0, y1):
    return VectorSegment(
        segment_id=seg_id, orientation="V", p1=(x, y0), p2=(x, y1),
        length_pt=abs(y1-y0), color_name="BLACK", rgb=(0,0,0),
        stroke_width=1.0, drawing_index=0, source_item_index=seg_id,
        is_near_black=True,
    )


class Dev7LayoutFeederRecoveryTests(unittest.TestCase):
    def test_repeated_top_level_vertical_trunks_recover_unresolved_feeders(self):
        segs = [
            _v(1, 100, 150, 700), _v(2, 300, 150, 700), _v(3, 500, 150, 700),
            # Lower equipment side: should be rejected by the upper-start coherence gate.
            _v(4, 200, 260, 700),
        ]
        r = recover_layout_feeder_candidates(_FakePage(), 1, "CI::T::LAYOUT", segs)
        self.assertEqual(len(r), 3)
        self.assertEqual([x["synthetic_line_key"] for x in r], [
            "LAYOUT_FEEDER_01", "LAYOUT_FEEDER_02", "LAYOUT_FEEDER_03"
        ])
        self.assertTrue(all(x["label_status"] == "UNRESOLVED" for x in r))

    def test_structural_feeders_group_cus_without_claiming_source_labels(self):
        feeders = []
        for i, x in enumerate((100, 300, 500), 1):
            feeders.append({
                "candidate_id": f"F{i}", "synthetic_line_key": f"LAYOUT_FEEDER_{i:02d}",
                "bbox": [x-15, 125, x+15, 140], "trunk": {"x": x},
                "label_status": "UNRESOLVED", "raw_header_text": f"@@{i}",
            })
        anchors = []
        for n, x in enumerate((112, 118, 312, 318, 512, 518), 1):
            anchors.append({
                "equipment_type": "CONVERSION_UNIT", "anchor_role": "INSTANCE",
                "anchor_id": f"CU{n}", "text": f"CABINA {n}",
                "bbox": [x-5, 400, x+5, 410], "attributes": {"instance_hint": n},
            })
        page = {
            "page": 1, "doc": "CI::T::LAYOUT", "page_width_pt": 1000, "page_height_pt": 1000,
            "text_equipment_anchors": anchors, "layout_mv_line_anchors": [],
            "layout_feeder_candidates": feeders,
            "planar_graph": {"nodes": [], "edges": []},
        }
        r = resolve_layout([page])
        self.assertEqual(r["summary"]["mv_line_count"], 3)
        self.assertEqual(r["summary"]["resolved_cu_mv_membership_count"], 6)
        self.assertEqual(r["summary"]["unresolved_mv_line_label_count"], 3)
        self.assertEqual(r["unresolved_membership"], [])
        self.assertTrue(all(x["line_label_status"] == "UNRESOLVED" for x in r["cu_mv_membership"]))


if __name__ == "__main__":
    unittest.main()
