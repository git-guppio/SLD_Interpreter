"""Graphical combiner pattern: red bus + green protection + cyan enclosure."""
import unittest
from PIL import Image,ImageDraw
from sld_ci_v04_beta3.sap.cad_dc_combiner_alpha20 import classify_combiner_candidates


def fixture(*,cells=5, red=True,green=True):
    image=Image.new('RGB',(400,200),'white')
    draw=ImageDraw.Draw(image)
    left,top=20,40
    for i in range(cells):
        x=left+i*60
        draw.rectangle((x,top,x+60,top+40),outline=(0,255,255),width=2)
        if red:draw.line((x+7,top+21,x+53,top+21),fill=(255,0,0),width=2)
        if green:draw.rectangle((x+28,top+6,x+34,top+18),outline=(0,255,0),width=2)
    panels=[{'page':1,'bbox_px':[left,top,left+cells*60,top+41],
             'contained_cyan_compartments':cells}]
    fields=[{'page':1,'field_candidate':1,'panel_boxes_px':[[left,top,left+cells*60,top+41]],
             'compartments_observed':cells}]
    return image,fields,panels


class Alpha20CombinerTests(unittest.TestCase):
    def test_generic_cabinet_count_five_no_fixed_eight(self):
        img,f,p=fixture(cells=5)
        out=classify_combiner_candidates(img,f,p)[0]
        self.assertEqual(out['dc_combiner_like_cabinet_candidates'],5)
        self.assertTrue(out['all_graphic_compartments_meet_symbol_test'])
        self.assertIsNone(out['string_boxes_verified'])
        self.assertTrue(out['operator_semantic_mapping_required'])

    def test_no_green_protection_not_classified(self):
        img,f,p=fixture(green=False)
        out=classify_combiner_candidates(img,f,p)[0]
        self.assertEqual(out['dc_combiner_like_cabinet_candidates'],0)
        self.assertFalse(out['all_graphic_compartments_meet_symbol_test'])

    def test_no_red_bus_not_classified(self):
        img,f,p=fixture(red=False)
        out=classify_combiner_candidates(img,f,p)[0]
        self.assertEqual(out['dc_combiner_like_cabinet_candidates'],0)

    def test_only_matching_page_classified(self):
        img,f,p=fixture()
        self.assertEqual(classify_combiner_candidates(img,f,p,page_number=2),[])

    def test_missing_panel_does_not_create_cabinet(self):
        img,f,p=fixture()
        self.assertEqual(classify_combiner_candidates(img,f,[],page_number=1)[0]['dc_combiner_like_cabinet_candidates'],0)

if __name__=='__main__':unittest.main()
