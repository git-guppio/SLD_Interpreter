import tempfile
import unittest
from pathlib import Path

from sld_ci_v04_beta2_dev14c.workflow import discover_case, _compact_summary
from sld_ci_v04_beta2_dev14c.operator_simple import choose_next_task


class Dev14WorkflowTests(unittest.TestCase):
    def test_discover_split_sources(self):
        with tempfile.TemporaryDirectory() as td:
            c=Path(td); (c/'input').mkdir(); (c/'output').mkdir()
            (c/'input'/'PVX_SLD.pdf').write_bytes(b'x')
            (c/'input'/'PVX_LAYOUT.pdf').write_bytes(b'y')
            s,l,o,stem=discover_case(c)
            self.assertEqual(s.name,'PVX_SLD.pdf'); self.assertEqual(l.name,'PVX_LAYOUT.pdf'); self.assertEqual(stem,'PVX')

    def test_compact_summary(self):
        r={'target_counts':{'conversion_units':10,'mv_lv_transformers':10,'inverters':20,'string_boxes':50},
           'feeder_verification':{'summary':{'explicit_schedule_feeder_count':2,'graph_verified_cu_mv_membership_count':3,'fully_graph_verified_feeder_count':0,'end_to_end_graph_trace_complete_count':0}},
           'source_reconciliation':{'summary':{'mv_line_count':2,'resolved_cu_mv_membership_count':10,'membership_hard_conflict_count':0}}}
        s=_compact_summary(r)
        self.assertEqual(s['membership'],10); self.assertEqual(s['graph_verified'],3); self.assertEqual(s['feeders'],2)

    def test_next_task_root_then_xfr(self):
        req={'status':'OPEN','request_id':'R','context':{'feeders':[{'feeder_id':'MV-01','member_cu_instance_keys':['1']}]}}
        a={'feeder_verification_requests':[req],'feeder_verification':{'feeder_traces':[]}}
        self.assertEqual(choose_next_task(a,[])['kind'],'BIND_FEEDER_ROOT_PATTERN')
        fb=[{'value':{'action':'BIND_FEEDER_ROOT_PATTERN','feeder_id':'MV-01'}}]
        self.assertEqual(choose_next_task(a,fb)['kind'],'BIND_XFR_MV_TERMINAL_PATTERN')


    def test_legacy_unresolved_breakpoint_is_reoffered_under_new_schema(self):
        feeder={'feeder_id':'MV-01','member_cu_instance_keys':['1']}
        req={'status':'OPEN','request_id':'R','context':{'feeders':[feeder]}}
        a={'feeder_verification_requests':[req],'feeder_verification':{'feeder_traces':[]}}
        fb=[
            {'value':{'action':'BIND_FEEDER_ROOT_PATTERN','feeder_id':'MV-01'}},
            {'value':{'action':'BIND_XFR_MV_TERMINAL_PATTERN','feeder_id':'MV-01','xfr_instance_key':'1'}},
            {'value':{'action':'CLASSIFY_FEEDER_BREAKPOINT','classification':'UNRESOLVED','feeder_id':'MV-01','page':1,'source_node_id':10,'target_node_id':11,'point_a':[1,1],'point_b':[1,2]}},
        ]
        t=choose_next_task(a,fb)
        self.assertEqual(t['kind'],'CLASSIFY_FEEDER_BREAKPOINT')
        self.assertEqual(t['breakpoint']['source_node_id'],10)
        self.assertEqual(t.get('revisit_reason'),'LEGACY_UNRESOLVED_WITH_NEW_GRAPHIC_OPTION')

    def test_next_task_breakpoint(self):
        feeder={'feeder_id':'MV-01','member_cu_instance_keys':['1']}
        req={'status':'OPEN','request_id':'R','context':{'feeders':[feeder]}}
        bp={'page':1,'source_node_id':1,'target_node_id':2,'point_a':[1,1],'point_b':[1,2]}
        a={'feeder_verification_requests':[req],'feeder_verification':{'feeder_traces':[{'feeder_id':'MV-01','suggested_breakpoints':[bp]}]}}
        fb=[{'value':{'action':'BIND_FEEDER_ROOT_PATTERN','feeder_id':'MV-01'}},{'value':{'action':'BIND_XFR_MV_TERMINAL_PATTERN','feeder_id':'MV-01','xfr_instance_key':'1'}}]
        t=choose_next_task(a,fb)
        self.assertEqual(t['kind'],'CLASSIFY_FEEDER_BREAKPOINT'); self.assertEqual(t['breakpoint']['source_node_id'],1)

if __name__ == '__main__': unittest.main()
