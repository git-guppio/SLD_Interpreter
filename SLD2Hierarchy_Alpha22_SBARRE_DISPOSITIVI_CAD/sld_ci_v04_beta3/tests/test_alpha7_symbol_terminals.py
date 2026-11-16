"""Alpha7 tests: image-backed symbol hypotheses, collisions and nonverification."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from sld_ci_v04_beta3.integration.multistyle import audit_multistyle


class Alpha7Tests(unittest.TestCase):
    def newpdf(self, path, *, tags=('XFR-42',), rings=True, cable=True,
               second_pair=False, note=False, circles_far=False):
        with pymupdf.open() as doc:
            p=doc.new_page(width=700,height=550)
            for i,tag in enumerate(tags):
                p.insert_text((100,100+22*i),tag)
            if note:
                p.insert_text((100,116),'FIELD MET STATION')
                p.insert_text((100,131),'SEE SHEET E-231, DETAIL B')
            if rings:
                cx,cy=(490,400) if circles_far else (150,165)
                p.draw_circle((cx,cy),11)
                p.draw_circle((cx+20,cy),11)
                if cable:p.draw_line((cx+31,cy),(cx+95,cy))
            if second_pair:
                p.draw_circle((150,125),11)
                p.draw_circle((170,125),11)
                p.draw_line((181,125),(245,125))
            doc.save(path)

    def audit(self,kw):
        with TemporaryDirectory() as folder:
            p=Path(folder)/'fixture.pdf'
            self.newpdf(p,**kw)
            return audit_multistyle(p,max_probe_pages=1,regions_per_page=4)

    def test_pair_of_bezier_rings_and_vector_contact_are_only_candidates(self):
        result=self.audit({})
        stats=result['summary']
        self.assertEqual(stats['alpha7_unique_pair_drawings_unverified'],1)
        self.assertEqual(stats['alpha7_possible_edge_contacts_unverified'],1)
        probe=result['pages'][0]['local_vector_reviews'][0]['alpha7_symbol_terminal']
        self.assertEqual(probe['decision'],'SINGLE_PAIRED_CIRCLE_SYMBOL_CANDIDATE')
        self.assertEqual(probe['possible_contact_points'][0]['source_stroke_id'],'P1_D2_I0')
        self.assertFalse(probe['possible_contact_points'][0]['terminal_verified'])
        self.assertEqual(probe['through_device_paths_verified'],0)
        self.assertEqual(stats['graph_verified_feeder_memberships'],0)

    def test_label_alone_cannot_create_transformer(self):
        result=self.audit({'rings':False,'cable':False})
        self.assertEqual(result['summary']['alpha7_paired_circle_symbol_candidates'],0)
        self.assertEqual(result['pages'][0]['local_vector_reviews'][0]['alpha7_symbol_terminal']['decision'],'NO_PAIRED_CIRCLE_SYMBOL')

    def test_far_ornamental_rings_are_not_bound(self):
        result=self.audit({'circles_far':True})
        self.assertEqual(result['summary']['alpha7_paired_circle_symbol_candidates'],0)

    def test_drawing_note_does_not_create_asset_or_terminals(self):
        result=self.audit({'rings':False,'cable':False,'note':True})
        review=result['pages'][0]['local_vector_reviews'][0]['alpha7_symbol_terminal']
        self.assertEqual(review['decision'],'DRAWING_NOTE_REVIEW')
        self.assertTrue(review['drawing_note_cues'])
        self.assertFalse(review['symbol_physical_identity_verified'])
        self.assertEqual(review['device_terminals_verified'],0)

    def test_two_tags_near_same_rings_flag_collision_without_duplicating_asset(self):
        result=self.audit({'tags':['XFR-42','XFR-43']})
        stats=result['summary']
        self.assertEqual(stats['alpha7_unique_pair_drawings_unverified'],1)
        self.assertEqual(stats['alpha7_symbol_tag_collision_regions'],2)
        self.assertEqual(stats['alpha7_possible_edge_contacts_unverified'],0)
        for rev in result['pages'][0]['local_vector_reviews']:
            self.assertEqual(rev['alpha7_symbol_terminal']['decision'],'SAME_SYMBOL_CANDIDATE_FOR_MULTIPLE_TAGS')
        self.assertIsNone(result['count_provenance']['canonical_physical_asset_count'])

    def test_multiple_symbols_no_arbitrary_terminal_selection(self):
        result=self.audit({'second_pair':True})
        review=result['pages'][0]['local_vector_reviews'][0]['alpha7_symbol_terminal']
        self.assertEqual(review['decision'],'MULTIPLE_SYMBOL_HYPOTHESES_NEEDS_REVIEW')
        self.assertEqual(review['possible_contact_points'],[])

    def test_mere_swgr_tag_is_not_assigned_transformer_pattern(self):
        result=self.audit({'tags':['ABC-CTR-01']})
        review=result['pages'][0]['local_vector_reviews'][0]['alpha7_symbol_terminal']
        self.assertEqual(review['decision'],'SYMBOL_CLASS_NOT_IMPLEMENTED')
        self.assertEqual(review['symbol_hypotheses'],[])

    def test_dash_never_becomes_terminal(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'dash.pdf'
            with pymupdf.open() as doc:
                page=doc.new_page(width=700,height=550)
                page.insert_text((100,100),'XFR-42')
                page.draw_circle((150,165),11)
                page.draw_circle((170,165),11)
                sh=page.new_shape()
                sh.draw_line((181,165),(250,165))
                sh.finish(color=(0,0,0),dashes='[3 3] 0')
                sh.commit()
                doc.save(path)
            result=audit_multistyle(path)
            review=result['pages'][0]['local_vector_reviews'][0]['alpha7_symbol_terminal']
            self.assertEqual(review['possible_contact_points'],[])
            self.assertEqual(result['summary']['graph_verified_feeder_memberships'],0)

if __name__ == '__main__':unittest.main()
