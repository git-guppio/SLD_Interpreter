import unittest
import pymupdf as fitz

from sld_ci_v04_beta2_dev14c.operator_visual import (
    _open_visual_requests,
    _visual_hints,
    pdf_rect_to_rotated_page,
    rotated_page_rect_to_pdf,
)
from sld_ci_v04_beta2_dev14c.resolution_engine import build_resolution_requests


class Dev3VisualTests(unittest.TestCase):
    def test_visual_hints_are_emitted(self):
        pages = [{"doc": "CI::PVX", "page": 2, "text_equipment_anchors": []}]
        profiles = [{
            "group_id": "G1",
            "document": "CI::PVX",
            "page": 2,
            "candidate_type": "PAIRED_CIRCLE_ELECTRICAL_CANDIDATE",
            "scope_status": "IN_SCOPE",
            "geometry": {"bbox": [10, 20, 30, 40]},
            "repetition": {"morph_family_id": "MF_1", "family_size": 5},
            "topology": {"terminal_count": 2},
        }]
        reqs = build_resolution_requests(pages, profiles, [], container_resolution={"entities": []})
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["page"], 2)
        self.assertEqual(reqs[0]["context"]["visual_hints"][0]["group_id"], "G1")
        analysis = {"interpretation": {"resolution_requests": reqs, "candidate_feature_profiles": profiles}}
        self.assertEqual(len(_open_visual_requests(analysis)), 1)
        hint = _visual_hints(reqs[0], analysis)[0]
        self.assertEqual(hint.bbox, [10.0, 20.0, 30.0, 40.0])

    def test_rotated_coordinate_roundtrip(self):
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        page.set_rotation(90)
        source = [20, 10, 80, 40]
        rotated = pdf_rect_to_rotated_page(page, source)
        back = rotated_page_rect_to_pdf(page, rotated)
        got = [round(v, 6) for v in (back.x0, back.y0, back.x1, back.y1)]
        self.assertEqual(got, [20.0, 10.0, 80.0, 40.0])


if __name__ == "__main__":
    unittest.main()
