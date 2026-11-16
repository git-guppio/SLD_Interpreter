"""Independent AFTER-THE-FACT comparator; never called by inference.

The operator's reference remains outside the candidate extraction pipeline.
Results distinguish matching TOTAL quantities from correct per-inverter mapping.
"""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path


def compare_pampa_format(report_path, reference_path, out_path):
    report=json.loads(Path(report_path).read_text(encoding='utf-8-sig'))
    ref=Path(reference_path).read_text(encoding='utf-8-sig')
    truth={}
    for cu,tr,inv,sb in re.findall(r'CU\s*(\d+)\s*-\s*TR\s*(\d+)\s*-\s*INV\s*(\d+)\s*-\s*SB\s*(\d+)',ref,re.I):
        key=(int(cu),int(inv))
        if key in truth:raise ValueError('Chiave duplicata nel riferimento')
        truth[key]={'tr':int(tr),'sb':int(sb)}
    if not truth:raise ValueError('Nessuna riga CU-TR-INV-SB utilizzabile nel TXT')
    observed={}
    for row in report['assets']:
        if row['type']!='STRING_BOX_QUANTITY':continue
        m=re.search(r'::INV::(\d+)\.(\d+)$',row['parent_id'])
        if not m:continue
        key=tuple(map(int,m.groups()))
        if key in observed:raise ValueError('Quantita duplicate per inverter nel report')
        observed[key]={'sb':row['quantity'],'ref':row['evidence_ref']}
    comparison=[]
    for key in sorted(set(truth)|set(observed)):
        a=truth.get(key,{});b=observed.get(key,{})
        status='MATCH' if a.get('sb')==b.get('sb') else 'DIFFERENT'
        comparison.append({'cu_id':key[0],'inverter_slot':key[1],
                           'gt_tr_slot':a.get('tr',''), 'gt_sb':a.get('sb',''),
                           'pdf_sb':b.get('sb',''), 'status':status,
                           'pdf_evidence_ref':b.get('ref','')})
    out=Path(out_path);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(comparison[0]),delimiter=';')
        w.writeheader();w.writerows(comparison)
    return {'reference_rows':len(truth),'pdf_rows':len(observed),
            'reference_total_sb':sum(a['sb'] for a in truth.values()),
            'pdf_total_sb':sum(a['sb'] for a in observed.values()),
            'per_inverter_matching':sum(r['status']=='MATCH' for r in comparison),
            'per_inverter_total':len(comparison),
            'mismatches':[(r['cu_id'],r['inverter_slot'],r['gt_sb'],r['pdf_sb'])
                          for r in comparison if r['status']!='MATCH']}
