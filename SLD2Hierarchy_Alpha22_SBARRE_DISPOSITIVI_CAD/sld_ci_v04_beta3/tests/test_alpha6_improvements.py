"""Alpha6 regression tests: dense ROI, index, dash diagnostics, tag provenance, honest P/R."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pymupdf
from sld_ci_v04_beta3.integration.multistyle import audit_multistyle, summarize_tag_identities
from sld_ci_v04_beta3.integration.corpus_benchmark import compare_annotated_tags
from sld_ci_v04_beta3.geometry.kernel import Stroke, build_graph
from sld_ci_v04_beta3.geometry.dash_patterns import find_microdash_candidates
from sld_ci_v04_beta3.geometry.spatial_index import SegmentIndex

class Alpha6Tests(unittest.TestCase):
    def stroke(self,i,a,b,dash=False):return Stroke(str(i),a,b,(0,0,0),1,dash)

    def test_sparse_kernel_broadphase_not_n_squared(self):
        ss=[self.stroke(i,(i*40.,0.),(i*40.,10.)) for i in range(350)]
        out=build_graph(ss)
        self.assertEqual(out['component_count'],350)
        self.assertLess(out['broadphase_pair_checks'],350)
        self.assertEqual(out['potential_pairs_without_index'],350*349//2)

    def test_long_line_in_index_not_lost(self):
        ss=[self.stroke(0,(0,0),(1500,0))]
        ss += [self.stroke(i+1,(i*50,-10),(i*50,10)) for i in range(1,15)]
        idx=SegmentIndex(ss,cell_size=5,max_cells_per_item=5)
        self.assertEqual(len(idx.query_indices(ss[0])),len(ss))
        r=build_graph(ss,dots=[])
        self.assertEqual(r['component_count'],15) # geometric crossings do not join absent dots
        self.assertTrue(any(not k['connected'] for k in r['crossings']))

    def test_dash_chain_detected_without_bridging(self):
        ss=[self.stroke(i,(i*5.,0),(i*5.+2.,0)) for i in range(5)]
        matches=find_microdash_candidates(ss)
        self.assertEqual(len(matches),1)
        self.assertFalse(matches[0]['electrical_continuity_verified'])
        self.assertEqual(build_graph(ss)['component_count'],5)

    def test_touching_short_strokes_not_dash_pattern(self):
        ss=[self.stroke(i,(i*2.,0),(i*2.+2.,0)) for i in range(5)]
        self.assertEqual(find_microdash_candidates(ss),[])
        self.assertEqual(build_graph(ss)['component_count'],1)

    def test_dense_page_local_roi_not_globally_declined(self):
        with TemporaryDirectory() as d:
            pdf=Path(d)/'dense.pdf'
            with pymupdf.open() as doc:
                p=doc.new_page(width=700,height=600)
                p.insert_text((100,100),'XFR-42')
                p.draw_line((100,125),(180,125))
                for j in range(150):
                    # 150 irrelevant drawings far from the ROI
                    p.draw_line((450,j+200),(465,j+200))
                doc.save(pdf)
            result=audit_multistyle(pdf,max_drawings=10)
            rev=result['pages'][0]['local_vector_reviews'][0]
            self.assertGreater(rev['page_total_vector_drawings'],10)
            self.assertEqual(result['pages'][0]['geometry_status'],'COMPLETE_DIAGNOSTIC')
            self.assertEqual(rev['status'],'VECTOR_NEIGHBORHOOD_CANDIDATE')
            self.assertGreater(rev['solid_line_segments_overlapping_roi'],0)
            self.assertEqual(result['summary']['graph_verified_feeder_memberships'],0)

    def test_per_roi_cap_does_not_masquerade_as_success(self):
        with TemporaryDirectory() as d:
            pdf=Path(d)/'dense_roi.pdf'
            with pymupdf.open() as doc:
                p=doc.new_page(width=700,height=600)
                p.insert_text((100,100),'XFR-42')
                for i in range(25):p.draw_line((100,115+i),(160,115+i))
                doc.save(pdf)
            r=audit_multistyle(pdf,max_drawings=5)
            self.assertEqual(r['pages'][0]['geometry_status'],'PARTIAL_ROI_SAFETY_CAP')
            self.assertEqual(r['pages'][0]['local_vector_reviews'][0]['status'],'ROI_COMPLEXITY_SAFETY_CAP')
            self.assertEqual(r['summary']['roi_safety_cap_regions'],1)

    def test_tag_repeats_have_source_provenance_not_two_assets(self):
        pages=[{'named_devices':[{'tag_type':'TRANSFORMER_TAG','tag':'XFR-5','page':1,'bbox':[1,2,3,4],'source':'NATIVE_PDF_TEXT'}]},
               {'named_devices':[{'tag_type':'TRANSFORMER_TAG','tag':'XFR-5','page':2,'bbox':[7,8,9,10],'source':'NATIVE_PDF_TEXT'}]}]
        r=summarize_tag_identities(pages)
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['mention_count'],2)
        self.assertEqual(r[0]['identity_status'],'REPEATED_TAG_REQUIRES_IDENTITY_REVIEW')
        self.assertEqual(len(r[0]['occurrences']),2)

    def test_safe_xfr_format_variants_grouped_as_same_tag_key(self):
        pages=[{'named_devices':[{'tag_type':'TRANSFORMER_TAG','tag':'XFR 111','page':1,'bbox':[1,2,3,4],'source':'NATIVE_PDF_TEXT'}]},
               {'named_devices':[{'tag_type':'TRANSFORMER_TAG','tag':'XFR-111','page':2,'bbox':[7,8,9,10],'source':'NATIVE_PDF_TEXT'}]}]
        r=summarize_tag_identities(pages)
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['tag'],'XFR-111')
        self.assertEqual(set(r[0]['observed_tag_spellings']),{'XFR-111','XFR 111'})

    def test_count_only_benchmark_cannot_score_precision(self):
        a={'tag_identity_groups':[{'tag_type':'TRANSFORMER_TAG','tag':'XFR-1'}]}
        x=compare_annotated_tags(a,None)
        self.assertIsNone(x['physical_asset_precision'])
        self.assertIsNone(x['tag_level_recall'])

    def test_same_count_can_have_false_positives_and_negatives(self):
        a={'tag_identity_groups':[{'tag_type':'TRANSFORMER_TAG','tag':'XFR-1'},
                                   {'tag_type':'TRANSFORMER_TAG','tag':'XFR-2'}]}
        x=compare_annotated_tags(a,[{'tag_type':'TRANSFORMER_TAG','tag':'XFR-1'},
                                     {'tag_type':'TRANSFORMER_TAG','tag':'XFR-3'}])
        self.assertEqual((x['TP'],x['FP'],x['FN']),(1,1,1))
        self.assertEqual(x['tag_level_precision'],.5)
        self.assertEqual(x['tag_level_recall'],.5)
        self.assertIsNone(x['physical_asset_precision'])

    def test_never_adds_tables_and_shapes_as_fake_count(self):
        with TemporaryDirectory() as d:
            pdf=Path(d)/'simple.pdf'
            with pymupdf.open() as doc:
                p=doc.new_page();p.insert_text((100,100),'XFR-99');doc.save(pdf)
            r=audit_multistyle(pdf)
            counts=r['count_provenance']
            self.assertEqual(counts['native_pdf_tag_mentions'],1)
            self.assertIsNone(counts['explicit_table_asset_count'])
            self.assertIsNone(counts['canonical_physical_asset_count'])

if __name__=='__main__':unittest.main()
