"""Post-inference-only comparison of TR/Inverter parent proposals vs operator TXT.

Never imported by parentage_alpha11.py or label_first.py. Count agreement
cannot substitute a per-inverter ID comparison or path proof.
"""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path

PATTERN=re.compile(r'CU\s*(\d+)\s*-\s*TR\s*(\d+)\s*-\s*INV\s*(\d+)\s*-\s*SB\s*(\d+)',re.I)


def compare_parents(proposals_path, reference_path, output_csv):
    prop=json.loads(Path(proposals_path).read_text(encoding='utf-8-sig'))
    reference=Path(reference_path).read_text(encoding='utf-8-sig')
    truth={}
    for cu,tr,inv,sb in PATTERN.findall(reference):
        key=(int(cu),int(inv))
        if key in truth:raise ValueError('Duplicated operator reference for '+str(key))
        truth[key]=(int(tr),int(sb))
    if not truth:raise ValueError('No valid CU-TR-INV-SB reference lines')
    predicted={}
    for item in prop['candidates']:
        key=(int(item['cu_number']),int(item['inverter_slot']))
        if key in predicted:raise ValueError('Duplicated automatic proposal for '+str(key))
        predicted[key]=int(item['transformer_slot'])
    rows=[]
    for key in sorted(set(truth)|set(predicted)):
        expected=truth.get(key)
        actual=predicted.get(key)
        status='MATCH' if expected and actual==expected[0] else ('MISSING_PROPOSAL' if actual is None else 'DIFFERENT_PARENT' if expected else 'NOT_IN_REFERENCE')
        rows.append({'cu':key[0],'inverter':key[1],
                     'reference_tr':expected[0] if expected else '',
                     'proposal_tr':actual if actual is not None else '',
                     'status':status})
    p=Path(output_csv);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['cu','inverter','reference_tr','proposal_tr','status'],delimiter=';')
        w.writeheader();w.writerows(rows)
    matches=sum(r['status']=='MATCH' for r in rows)
    return {'matches':matches,'total_comparison_rows':len(rows),
            'expected_rows':len(truth),'candidate_rows':len(predicted),
            'mismatches':[r for r in rows if r['status']!='MATCH']}
