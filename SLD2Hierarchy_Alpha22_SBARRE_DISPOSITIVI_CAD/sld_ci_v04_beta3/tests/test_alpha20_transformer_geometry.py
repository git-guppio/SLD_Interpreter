"""Generic CAD black-circle pair recognition and abstention tests."""
import math
import tempfile
import unittest
from pathlib import Path
try:
    import pymupdf as fitz
except ImportError:
    import fitz
from sld_ci_v04_beta3.sap.cad_transformer_geometry_alpha20 import (
    find_vector_circle_shapes,double_winding_candidates,candidate_upstream_tr_winding_pairs)


def poly_circle(page,cx,cy,r,color=(0,0,0)):
    points=[fitz.Point(cx+r*math.cos(2*math.pi*i/28),
                       cy+r*math.sin(2*math.pi*i/28)) for i in range(29)]
    shape=page.new_shape();shape.draw_polyline(points)
    shape.finish(color=color,width=1,closePath=True);shape.commit()


def leads(x):
    return [{'upstream_terminal_px':[x-9,130]},
            {'upstream_terminal_px':[x,130]},
            {'upstream_terminal_px':[x+9,130]}]

class Alpha20TransformerTests(unittest.TestCase):
    def test_double_circle_candidate_and_nonverified_parent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'generic.pdf';doc=fitz.open();page=doc.new_page(width=300,height=200)
            poly_circle(page,145,75,9);poly_circle(page,156,75,9)
            doc.save(p);doc.close()
            with fitz.open(p) as doc:
                rings=find_vector_circle_shapes(doc[0]);pairs=double_winding_candidates(rings)
            self.assertEqual(len(rings),2)
            self.assertEqual(len(pairs),1)
            hyp=candidate_upstream_tr_winding_pairs(pairs,leads(150))
            self.assertEqual(hyp['status'],'ONE_AXIAL_TR_WINDING_HYPOTHESIS')
            self.assertIsNone(hyp['tr_parent'])
            self.assertFalse(hyp['electric_path_across_device_verified'])

    def test_red_ring_not_classified_as_transformer(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'generic.pdf';doc=fitz.open();page=doc.new_page(width=300,height=200)
            poly_circle(page,145,75,9,color=(1,0,0));poly_circle(page,156,75,9,color=(1,0,0))
            doc.save(p);doc.close()
            with fitz.open(p) as doc:
                self.assertEqual(find_vector_circle_shapes(doc[0]),[])

    def test_no_axis_match_abstains(self):
        pairs=[{'center_px':[10,20]}]
        r=candidate_upstream_tr_winding_pairs(pairs,leads(150))
        self.assertEqual(r['status'],'NO_WINDING_PAIR_ON_COMMON_FEEDER_AXIS')
        self.assertIsNone(r['tr_parent'])

    def test_two_axial_candidates_are_ambiguous(self):
        pairs=[{'center_px':[148,40]},{'center_px':[152,65]}]
        r=candidate_upstream_tr_winding_pairs(pairs,leads(150))
        self.assertEqual(r['status'],'MULTIPLE_AXIAL_WINDING_HYPOTHESES')
        self.assertEqual(len(r['candidates']),2)
        self.assertIsNone(r['tr_parent'])

    def test_no_inverter_leads_no_candidate(self):
        r=candidate_upstream_tr_winding_pairs([{'center_px':[100,40]}],[])
        self.assertEqual(r['status'],'NO_TRACED_INPUT_FEEDER')

if __name__=='__main__':unittest.main()
