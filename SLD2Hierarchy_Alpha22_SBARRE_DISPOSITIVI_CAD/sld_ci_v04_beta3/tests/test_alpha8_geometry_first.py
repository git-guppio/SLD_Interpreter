"""Alpha8 independent geometry-first tests; no ground-truth expectations enter inference."""
from __future__ import annotations
import math, tempfile, unittest
from pathlib import Path

import pymupdf
from sld_ci_v04_beta3.integration.geometry_first import (_circle_like, group_circles,
    inspect_page_geometry)
from sld_ci_v04_beta3.integration.multistyle import audit_multistyle


def polygon_circle(cx,cy,r=12,n=36):
    points=[(cx+r*math.cos(j*2*math.pi/n),cy+r*math.sin(j*2*math.pi/n)) for j in range(n+1)]
    return {'type':'s','rect':(cx-r,cy-r,cx+r,cy+r),'dashes':'[] 0',
            'items':[('l',points[i],points[i+1]) for i in range(n)]}


class FakePage:
    def __init__(self,drawings):self.drawings=drawings
    def get_cdrawings(self):return self.drawings


class Alpha8GeometryFirstTests(unittest.TestCase):
    def test_three_polygon_rings_unlabeled_group(self):
        cs=[_circle_like(polygon_circle(x,y),i) for i,(x,y) in enumerate(((40,40),(64,40),(52,60)))]
        self.assertTrue(all(cs))
        groups,omitted=group_circles(cs,page_number=9)
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['circle_drawing_ids'],[0,1,2])
        self.assertFalse(groups[0]['asset_verified'])
        self.assertFalse(groups[0]['terminal_verified'])
        self.assertEqual(omitted,0)

    def test_separate_group_not_merged(self):
        locs=[(40,40),(64,40),(52,60),(180,40),(204,40),(192,60)]
        cs=[_circle_like(polygon_circle(x,y),i) for i,(x,y) in enumerate(locs)]
        groups,_=group_circles(cs,page_number=1)
        self.assertEqual(len(groups),2)

    def test_open_micro_dash_is_not_ring(self):
        d=polygon_circle(30,30)
        d['items']=d['items'][:-2]
        self.assertIsNone(_circle_like(d,1))

    def test_jagged_non_round_closed_path_rejected(self):
        d=polygon_circle(30,30)
        items=d['items'];start=items[0][1]
        d['items']=[('l',start,items[1][2])] + items[2:-1]+[('l',items[-2][2],start)]
        self.assertIsNone(_circle_like(d,1))

    def test_dashed_circle_rejected(self):
        d=polygon_circle(30,30);d['dashes']='[4 3] 0'
        self.assertIsNone(_circle_like(d,1))

    def test_single_circle_does_not_claim_transformer(self):
        r=inspect_page_geometry(FakePage([polygon_circle(30,30)]),page_number=3)
        self.assertEqual(r['circles_detected'],1)
        self.assertEqual(r['group_count_total'],0)
        self.assertEqual(r['physical_assets_verified'],0)

    def test_geometry_scan_does_not_need_native_text(self):
        r=inspect_page_geometry(FakePage([polygon_circle(20,30),polygon_circle(44,30)]),page_number=8)
        self.assertEqual(r['status'],'COMPLETE_VECTOR_SHAPE_SCAN')
        self.assertEqual(r['group_count_total'],1)
        self.assertTrue(r['source_scan_complete'])
        self.assertEqual(r['graph_verified_feeder_memberships'],0)

    def test_safety_cap_declines_without_false_coverage(self):
        r=inspect_page_geometry(FakePage([polygon_circle(i*30,20) for i in range(3)]),
                                page_number=1,max_drawings=2)
        self.assertEqual(r['status'],'PAGE_VECTOR_SAFETY_CAP')
        self.assertFalse(r['source_scan_complete'])
        self.assertIsNone(r['group_count_total'])

    def test_review_budget_reports_omission(self):
        cs=[_circle_like(polygon_circle(x,y),i) for i,(x,y) in enumerate(((40,40),(64,40),(180,40),(204,40)))]
        groups,omitted=group_circles(cs,page_number=1,max_groups=1)
        self.assertEqual(len(groups),1)
        self.assertEqual(omitted,1)

    def test_realistic_no_native_text_pdf_launches_geometry_scan(self):
        with tempfile.TemporaryDirectory() as td:
            pdf=Path(td)/'tiny.pdf'
            doc=pymupdf.open(); page=doc.new_page(width=200,height=150)
            for cx,cy in ((50,70),(74,70),(62,90)):
                shape=page.new_shape()
                pts=[pymupdf.Point(cx+12*math.cos(j*math.pi/18),cy+12*math.sin(j*math.pi/18)) for j in range(37)]
                for a,b in zip(pts,pts[1:]):shape.draw_line(a,b)
                shape.finish(color=(0,0,0));shape.commit()
            doc.save(pdf);doc.close()
            r=audit_multistyle(pdf,max_probe_pages=2,geometry_first_pages=1)
            self.assertEqual(r['summary']['pages_without_native_text'],1)
            self.assertEqual(r['summary']['alpha8_geometry_first_pages_attempted'],1)
            self.assertTrue(r['pages'][0]['geometry_first']['source_scan_complete'])
            self.assertEqual(r['summary']['graph_verified_feeder_memberships'],0)

    def test_geometry_path_is_opt_in_legacy_unmodified(self):
        with tempfile.TemporaryDirectory() as td:
            pdf=Path(td)/'empty.pdf';doc=pymupdf.open();doc.new_page();doc.save(pdf);doc.close()
            r=audit_multistyle(pdf)
            self.assertEqual(r['pages'][0]['geometry_first']['status'],'NOT_REQUESTED')
            self.assertEqual(r['summary']['alpha8_geometry_first_pages_attempted'],0)

if __name__=='__main__':unittest.main()
