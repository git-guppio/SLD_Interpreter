"""Alpha22 negative tests: abstention is preferable to false TR parentage."""
import tempfile
import fitz
import unittest
from pathlib import Path
from sld_ci_v04_beta3.sap.cad_bus_provenance_alpha22 import (
    audit_bus_and_winding,identify_common_buses,match_winding_to_bus,
    detect_series_apparatus_motifs,write_alpha22_reports)


def setup(n=3, *, bus_y=60.0, lead_y=73.0, bus=True, winding=True):
    xs=[40+20*i for i in range(n)]
    seg=[]
    if bus:seg.append(((min(xs),bus_y),(max(xs),bus_y)))
    # Each inverter's input lead is itself verified by Alpha20, and terminates
    # downstream of the bus; none of these gaps is silently bridged.
    for x in xs:seg.append(((x,lead_y),(x,lead_y+20)))
    if winding:seg.append(((xs[len(xs)//2],10),(xs[len(xs)//2],bus_y-8)))
    runs=[{'page':1,'status':'SOLID_CONDUCTOR_TO_OPEN_UPSTREAM_TERMINAL',
           'converter_candidate_id':f'INV_{i+1}', 'upstream_terminal_px':[x,lead_y]}
          for i,x in enumerate(xs)]
    wp=[{'page':1,'local_upstream_winding_hypotheses':{'candidates':[
        {'center_px':[xs[len(xs)//2],0], 'source_path_indices':[10,12]}]}}] if winding else []
    return seg,runs,wp


class BusEvidenceTests(unittest.TestCase):
    def test_variable_fanout_and_source_bus(self):
        for n in (2,3,4,7):
            with self.subTest(n=n):
                s,r,w=setup(n)
                result=audit_bus_and_winding(s,r,w)
                b=result['busbar_evidence']['bus']
                self.assertEqual(b['source_stroke_index'],0)
                self.assertEqual(b['members_count'],n)
                self.assertEqual(len(result['converter_with_source_lead_and_bus_candidate']),n)
                self.assertTrue(all(x['gap_unbridged'] for x in b['members']))
                self.assertFalse(result['transformer_parentage_claimed'])
                self.assertEqual(result['tr_inverter_automatically_verified'],0)

    def test_source_winding_wire_can_be_supported_but_never_electrically_verified(self):
        s,r,w=setup()
        a=audit_bus_and_winding(s,r,w)
        self.assertEqual(a['winding_evidence']['status'],'ONE_WINDING_PAIR_AND_SECONDARY_WIRE_WITH_UNBRIDGED_GAP')
        self.assertEqual(a['winding_evidence']['transformer']['secondary_source_stroke_index'],4)
        self.assertFalse(a['winding_evidence']['electrical_path_verified'])
        self.assertEqual(a['bridges_through_switches_or_transformer_created'],0)

    def test_no_bus_refuses_to_invent_parent(self):
        s,r,w=setup(bus=False)
        a=audit_bus_and_winding(s,r,w)
        self.assertIsNone(a['busbar_evidence']['bus'])
        self.assertIsNone(a['winding_evidence']['transformer'])

    def test_partial_bus_cover_is_not_unique_full_span(self):
        s,r,w=setup()
        s[0]=((40,60),(60,60))
        self.assertEqual(identify_common_buses(s,r)['status'],'NO_UNIQUE_FULL_SPAN_SOURCE_BUSBAR')

    def test_gap_out_of_range_rejected(self):
        s,r,w=setup(lead_y=110)
        self.assertIsNone(identify_common_buses(s,r)['bus'])

    def test_multiple_parallel_buses_are_ambiguous(self):
        s,r,w=setup()
        s.append(((40,61),(80,61)))
        a=identify_common_buses(s,r)
        self.assertEqual(a['status'],'AMBIGUOUS_PARALLEL_BUSBARS')
        self.assertIsNone(a['bus'])

    def test_dashed_text_or_wrong_axis_never_becomes_bus(self):
        s,r,w=setup()
        s[0]=((40,60),(80,65))
        self.assertIsNone(identify_common_buses(s,r)['bus'])

    def test_missing_winding_or_source_secondary_wire_keeps_no_transformer(self):
        s,r,w=setup(winding=False)
        a=audit_bus_and_winding(s,r,w)
        self.assertEqual(a['winding_evidence']['status'],'NO_WINDING_WITH_SOURCE_WIRE_NEAR_BUS')
        self.assertIsNone(a['winding_evidence']['transformer'])

    def test_cross_page_leads_cannot_form_source_bus(self):
        s,r,w=setup()
        r[2]['page']=2
        a=audit_bus_and_winding(s,r,w,page=1)
        self.assertEqual(a['busbar_evidence']['bus']['members_count'],2)
        self.assertNotIn('INV_3',a['converter_with_source_lead_and_bus_candidate'])

    def test_upstream_circuit_different_x_cannot_claim_transformer(self):
        s,r,w=setup()
        w[0]['local_upstream_winding_hypotheses']['candidates'][0]['center_px']=[900,0]
        a=audit_bus_and_winding(s,r,w)
        self.assertIsNone(a['winding_evidence']['transformer'])

    def test_two_transformer_windings_dont_choose_one_arbitrarily(self):
        s,r,w=setup()
        w[0]['local_upstream_winding_hypotheses']['candidates'].append(
            {'center_px':[60,0],'source_path_indices':[30,32]})
        a=audit_bus_and_winding(s,r,w)
        self.assertEqual(a['winding_evidence']['status'],'AMBIGUOUS_MULTIPLE_WINDINGS_AT_BUS')
        self.assertIsNone(a['winding_evidence']['transformer'])

    def test_invalid_nonfinite_lead_not_electrical_evidence(self):
        s,r,w=setup()
        r[1]['upstream_terminal_px']=[float('nan'),73]
        self.assertIsNone(identify_common_buses(s,r)['bus'])

    def test_csv_report_has_unverified_status_and_no_source_fabrication(self):
        s,r,w=setup()
        record=audit_bus_and_winding(s,r,w)
        with tempfile.TemporaryDirectory() as td:
            # Empty page list skips imaging; report format itself is testable.
            document={'schema':'sld-alpha22-cad-bus-evidence/v1','pages':[record]}
            p=Path(td)/'synthetic.pdf';p.write_bytes(b'%PDF-stub')
            outputs=write_alpha22_reports(p,document,td)
            data=outputs['csv'].read_text(encoding='utf-8-sig')
            self.assertEqual(data.count('CANDIDATO_GEOMETRICO_NON_CONFERMATO'),3)
            self.assertNotIn('TR_VERIFICATO',data)
            self.assertTrue(outputs['report'].is_file())


class SourceSymbolTests(unittest.TestCase):
    def _scene(self, *, contacts=2, ambiguous=False):
        doc=fitz.open();page=doc.new_page(width=1000,height=1000)
        s,r,w=setup()
        audit=audit_bus_and_winding(s,r,w)
        locations=[(60,54.6),(40,67.5),(60,67.5),(80,67.5)]
        for xx,yy in locations:
            page.draw_rect(fitz.Rect(xx-1,yy-1.6,xx+1,yy+1.6),color=(0,1,0),width=.2)
            for k in range(contacts):
                page.draw_line(fitz.Point(xx-.2,yy-.8+k*.7),fitz.Point(xx+.2,yy-.7+k*.7),
                               color=(1,0,1),width=.13)
        if ambiguous:
            page.draw_rect(fitz.Rect(41,66,42.5,69),color=(0,1,0),width=.2)
            page.draw_line(fitz.Point(41.5,67),fitz.Point(42.1,67),color=(1,0,1),width=.1)
            page.draw_line(fitz.Point(41.5,68),fitz.Point(42.1,68),color=(1,0,1),width=.1)
        return doc,page,audit

    def test_four_source_colored_motifs_detected_but_not_bridged(self):
        doc,p,r=self._scene()
        try:
            items=detect_series_apparatus_motifs(p,r)
            self.assertEqual(len(items),4)
            self.assertTrue(all(x['status'].startswith('IN_LINE_DEVICE_LIKE') for x in items))
            self.assertTrue(all(not x['device_edge_created'] for x in items))
            self.assertEqual(len(set(x['outline_source_path_index'] for x in items)),4)
        finally:doc.close()

    def test_green_without_magenta_does_not_certify_series_device(self):
        doc,p,r=self._scene(contacts=0)
        try:self.assertEqual(detect_series_apparatus_motifs(p,r),[])
        finally:doc.close()

    def test_one_magenta_fragment_not_enough_for_source_motif(self):
        doc,p,r=self._scene(contacts=1)
        try:self.assertEqual(detect_series_apparatus_motifs(p,r),[])
        finally:doc.close()

    def test_ambiguous_two_distinct_symbols_in_one_gap_abstains(self):
        doc,p,r=self._scene(ambiguous=True)
        try:
            items=detect_series_apparatus_motifs(p,r)
            self.assertTrue(any(x['status']=='AMBIGUOUS_MULTIPLE_SYMBOLS_IN_GAP' for x in items))
            self.assertTrue(all(not x['device_edge_created'] for x in items))
        finally:doc.close()


if __name__=='__main__':unittest.main()
