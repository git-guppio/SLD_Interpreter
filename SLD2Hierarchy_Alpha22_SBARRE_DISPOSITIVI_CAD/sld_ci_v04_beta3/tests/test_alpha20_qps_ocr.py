"""One-pass local OCR parsing; never auto-map QPS to SAP String Box."""
import unittest
from sld_ci_v04_beta3.sap.cad_qps_ocr_alpha20 import (
    parse_qps_ocr_tsv, reconcile_qps_sequences,find_local_tesseract)

HEADER='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
def tsv(words):
    return HEADER+''.join(f'5\t1\t1\t1\t1\t{i}\t{j*90+5}\t10\t60\t15\t35\t{t}\n'
                          for i,(j,t) in enumerate(words,1))
def field(n=4):
    return {'field_candidate':1,'candidate_cabinet_evidence':[
        {'bbox_px':[i*90,0,(i+1)*90,40]} for i in range(n)]}

class Alpha20QpsTests(unittest.TestCase):
    def test_complete_numbered_sequence_plus_geometry(self):
        words=list(enumerate(['OPS-1-1/4','QPS-1-2/4','0PS-1-3/4','aPS-1-4/4']))
        parsed=parse_qps_ocr_tsv(tsv(words),image_bbox=[0,0,360,80],display_scale=1)
        row=reconcile_qps_sequences(parsed,[field()])[0]
        self.assertTrue(row['sequence_complete'])
        self.assertEqual(row['qps_documented_count'],4)
        self.assertIsNone(row['string_box_count_for_matrix_flow'])
        self.assertFalse(parsed[0]['ocr_prefix_exact'])
        self.assertEqual(parsed[1]['normalized_designator'],'QPS-1-2/4')

    def test_missing_ordinal_abstains(self):
        parsed=parse_qps_ocr_tsv(tsv(list(enumerate(['QPS-1-1/4','QPS-1-3/4','QPS-1-4/4']))),
                                 image_bbox=[0,0,360,80],display_scale=1)
        row=reconcile_qps_sequences(parsed,[field()])[0]
        self.assertFalse(row['sequence_complete'])
        self.assertIsNone(row['qps_documented_count'])

    def test_duplicate_ordinal_abstains(self):
        parsed=parse_qps_ocr_tsv(tsv(list(enumerate(['QPS-1-1/4','QPS-1-2/4','QPS-1-2/4','QPS-1-4/4']))),
                                 image_bbox=[0,0,360,80],display_scale=1)
        self.assertFalse(reconcile_qps_sequences(parsed,[field()])[0]['sequence_complete'])

    def test_wrong_denominator_abstains(self):
        parsed=parse_qps_ocr_tsv(tsv(list(enumerate(['QPS-1-1/8','QPS-1-2/8','QPS-1-3/8','QPS-1-4/8']))),
                                 image_bbox=[0,0,360,80],display_scale=1)
        self.assertIsNone(reconcile_qps_sequences(parsed,[field()])[0]['qps_documented_count'])

    def test_mixed_groups_abstains(self):
        parsed=parse_qps_ocr_tsv(tsv(list(enumerate(['QPS-1-1/4','QPS-1-2/4','QPS-2-3/4','QPS-1-4/4']))),
                                 image_bbox=[0,0,360,80],display_scale=1)
        self.assertFalse(reconcile_qps_sequences(parsed,[field()])[0]['sequence_complete'])

    def test_repeated_full_qps_group_across_two_fields_rejected(self):
        raw=tsv(list(enumerate(['QPS-1-1/2','QPS-1-2/2','QPS-1-1/2','QPS-1-2/2'])))
        tokens=parse_qps_ocr_tsv(raw,image_bbox=[0,0,360,80],display_scale=1)
        a={'field_candidate':1,'candidate_cabinet_evidence':[
            {'bbox_px':[0,0,90,40]},{'bbox_px':[90,0,180,40]}]}
        b={'field_candidate':2,'candidate_cabinet_evidence':[
            {'bbox_px':[180,0,270,40]},{'bbox_px':[270,0,360,40]}]}
        rows=reconcile_qps_sequences(tokens,[a,b])
        self.assertTrue(all(not r['sequence_complete'] for r in rows))
        self.assertTrue(all(r['source']=='DUPLICATE_QPS_GROUP_ACROSS_GRAPHIC_FIELDS' for r in rows))

    def test_non_qps_token_ignored(self):
        parsed=parse_qps_ocr_tsv(tsv([(0,'INV-1-1/4'),(1,'TR-1-2/4')]),
                                 image_bbox=[0,0,360,80],display_scale=1)
        self.assertEqual(parsed,[])

    def test_nonexistent_explicit_executable_abstains(self):
        self.assertIsNone(find_local_tesseract('/path/certainly/not/installed'))

if __name__=='__main__':unittest.main()
