"""Alpha15: second, generic documentary tag family for central-inverter PV SLDs.

No ground-truth file, plant-name lookup, or assumed fixed cardinality.
TR/INV tag-family matches are CANDIDATES, not conductive verification.
Distinct box identifiers give the count only for a complete 1..N sequence;
missing serials remain unresolved instead of guessing N.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

# Prefix is an arbitrary drawing-family identifier, not a hardcoded plant.
# Requiring indexed equipment tags avoids interpreting legend words as assets.
TR_RE = re.compile(r'\b([A-Z]{2,8})-(?:TPO|TR|TRAFO)-(\d{1,4})-(\d{1,4})\b',re.I)
INV_RE = re.compile(r'\b([A-Z]{2,8})-(?:INV|INVERTER)-(\d{1,4})-(\d{1,4})\b',re.I)
SB_RE = re.compile(r'\b([A-Z]{2,8})-(?:CST|CBX|SCB)-(\d{1,4})-I(\d{1,4})-(\d{1,3})-(\d{1,4})\b',re.I)
CT_RE = re.compile(r'(?:CENTRO\s+DE\s+TRANSFORMACI[OÓ]N\s+CT\s*[- ]\s*|CONVERSION\s+UNIT\s*[- ]\s*CU\s*[- ]\s*)(\d{1,4})',re.I)


def _evidence(pdf:Path,page:int,text:str,xy=None):
    out=f'{pdf.name}:p{page}:{text}'
    if xy:out+=f':xy=({xy[0]:.2f}, {xy[1]:.2f})'
    return out


def _first_coordinates(page, tag):
    # PyMuPDF search may not locate diagonally encoded CAD text. This is
    # evidence metadata only, never a prerequisite to recognition.
    rects=page.search_for(tag)
    return (rects[0].x0,rects[0].y0) if rects else None


def extract_indexed_families(pdf_path,plant_id):
    """Read native PDF text and cautiously stage source-labelled devices.

    The 4-column output is useful staging, not certified Matrix FLOW input.
    """
    pdf_path=Path(pdf_path)
    if not pdf_path.is_file():raise FileNotFoundError(pdf_path)
    plant=str(plant_id).removeprefix('CI::')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',plant):
        raise ValueError('Identificativo impianto non valido')
    trs={};invs={};sbs=defaultdict(dict);cu_refs=defaultdict(list);issues=[];page_info=[]
    with pymupdf.open(pdf_path) as doc:
        for pageno,page in enumerate(doc,1):
            content=page.get_text('text')
            page_info.append({'page':pageno,'native_characters':len(content),
                              'native_text':bool(content.strip())})
            for m in CT_RE.finditer(content):
                cu_refs[int(m.group(1))].append(_evidence(pdf_path,pageno,m.group(0)))
            for m in TR_RE.finditer(content):
                prefix,cu,tr=m.group(1).upper(),int(m.group(2)),int(m.group(3))
                key=(prefix,cu,tr)
                if key not in trs:
                    trs[key]={'id':m.group(0),'page':pageno,
                              'evidence':_evidence(pdf_path,pageno,m.group(0),_first_coordinates(page,m.group(0)))}
            for m in INV_RE.finditer(content):
                prefix,cu,slot=m.group(1).upper(),int(m.group(2)),int(m.group(3))
                key=(prefix,cu,slot)
                if key not in invs:
                    invs[key]={'id':m.group(0),'page':pageno,
                               'evidence':_evidence(pdf_path,pageno,m.group(0),_first_coordinates(page,m.group(0)))}
            for m in SB_RE.finditer(content):
                prefix,cu,slot,strings,serial=m.group(1).upper(),int(m.group(2)),int(m.group(3)),int(m.group(4)),int(m.group(5))
                key=(prefix,cu,slot)
                serial_ref=(prefix,cu,slot,serial)
                record={'id':m.group(0),'strings_per_box':strings,'page':pageno,
                        'evidence':_evidence(pdf_path,pageno,m.group(0),_first_coordinates(page,m.group(0)))}
                if serial in sbs[key] and sbs[key][serial]['id'].upper()!=record['id'].upper():
                    issues.append({'code':'BOX_SERIAL_COLLISION','device':key,'serial':serial,'page':pageno})
                else:
                    # Prefer a matching page for this inverter over references
                    # accidentally repeated in an unrelated sheet's notes.
                    old=sbs[key].get(serial)
                    if old is None or (key in invs and pageno==invs[key]['page'] and old['page']!=pageno):
                        sbs[key][serial]=record
    # Restrict a combiner-box tag to the inverter's own detailed SLD page:
    # an identical identifier in another page may be an index/note/legend.
    # Cross-page references require a future explicit document-link resolver.
    for key,records in list(sbs.items()):
        if key in invs:
            local={serial:r for serial,r in records.items() if r['page']==invs[key]['page']}
            if len(local)<len(records):
                issues.append({'code':'CROSS_PAGE_BOX_REFERENCE_IGNORED','inverter':invs[key]['id'],
                               'references_ignored':len(records)-len(local)})
            sbs[key]=local
    # CU identity is directly encoded in equipment tags, even if the text
    # header itself uses another language. Do not fabricate CU counts from
    # a general note, or interpret isolated CT header as an observed plant.
    cu_keys=sorted({(p,c) for p,c,_ in trs}|{(p,c) for p,c,_ in invs})
    cus=sorted({c for _,c in cu_keys})
    # TR slot candidates derived by exact same (prefix, CU, ordinal) only.
    rows=[]
    for (prefix,cu,original_inv),info in sorted(invs.items(),key=lambda z:z[0]):
        candidate_key=(prefix,cu,original_inv)
        transformer=trs.get(candidate_key)
        if transformer is None:
            candidate_tr=None
            issues.append({'code':'TR_PARENT_UNRESOLVED','inverter':info['id']})
        else:
            candidate_tr=original_inv
        records=sbs.get((prefix,cu,original_inv),{})
        serials=sorted(records)
        maximum=max(serials,default=None)
        missing=sorted(set(range(1,maximum+1))-set(serials)) if maximum else []
        if not records:
            quantity=None;sb_status='NESSUN_IDENTIFICATIVO_BOX_RILEVATO'
            issues.append({'code':'BOX_QUANTITY_UNRESOLVED','inverter':info['id']})
        elif missing:
            quantity=None;sb_status='SEQUENZA_BOX_INCOMPLETA'
            issues.append({'code':'BOX_SERIAL_GAP','inverter':info['id'],
                           'missing_serials':missing,'candidate_max':maximum})
        else:
            quantity=len(serials);sb_status='SEQUENZA_BOX_COMPLETA_1_N'
        rows.append({'CU':cu,'TR':candidate_tr,'INV':None,'STR_Box':quantity,
                     'prefix':prefix,'printed_inv_slot':original_inv,
                     'inv_id':info['id'],'tr_id':transformer['id'] if transformer else None,
                     'parent_status':'CANDIDATO_PER_CODIFICA' if transformer else 'NON_RISOLTO',
                     'sb_status':sb_status,'box_ids_observed':len(serials),'box_max_id':maximum,
                     'box_missing_ids':missing,'page':info['page'],
                     'inverter_evidence':info['evidence'],
                     'transformer_evidence':transformer['evidence'] if transformer else '',
                     'box_evidence':' | '.join(records[x]['evidence'] for x in serials)})
    # Assign INV numbering independently for every TR; no fanout limit.
    grouped=defaultdict(list)
    for row in rows:
        if row['TR'] is not None:
            grouped[(row['prefix'],row['CU'],row['TR'])].append(row)
    for _,sub in grouped.items():
        for pos,row in enumerate(sorted(sub,key=lambda r:r['printed_inv_slot']),1):
            row['INV']=pos
    for key in sorted(sbs):
        if key not in invs:
            issues.append({'code':'BOX_TAG_WITHOUT_INVERTER','tag_scope':key})
    for key in sorted(trs):
        if (key[0],key[1]) not in cu_keys:
            issues.append({'code':'TR_WITHOUT_CU','transformer':trs[key]['id']})
    return {'schema':'sld-sap-multistyle-alpha15/v1',
            'plant_id':'CI::'+plant,'source_pdf':str(pdf_path),
            'method':'indexed-native-tags / explicitly identified boxes',
            'pages':page_info,'cu_keys':cu_keys,'cus':cus,
            'transformers':[{'prefix':p,'CU':c,'TR':t,**v} for (p,c,t),v in sorted(trs.items())],
            'rows':rows,'issues':issues,
            'summary':{'cu':len(cus),'tr_candidate':len(trs),'inverters':len(invs),
                       'box_quantities_complete':sum(r['STR_Box'] is not None for r in rows),
                       'box_quantities_unresolved':sum(r['STR_Box'] is None for r in rows),
                       'box_quantity_total_complete_only':sum(r['STR_Box'] or 0 for r in rows),
                       'parent_candidates':sum(r['TR'] is not None for r in rows),
                       'parent_confirmed':0,'issue_count':len(issues)},
            'matrix_flow_import_ready':False,'electrical_connections_verified':0,
            'validation_status':'NOT_INDEPENDENTLY_VALIDATED'}


def write_csv_outputs(result,directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    (out/'alpha15_diagnostica.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    fields=['CU','TR','INV','STR_Box']
    with (out/'alpha15_CU_TR_INV_STR_Box.csv').open('w',newline='',encoding='utf-8-sig') as h:
        w=csv.DictWriter(h,fieldnames=fields,delimiter=';');w.writeheader()
        for r in result['rows']:w.writerow({k:'' if r[k] is None else r[k] for k in fields})
    evidence_fields=['CU','TR','INV','STR_Box','inv_id','tr_id','parent_status','sb_status',
                     'box_ids_observed','box_max_id','box_missing_ids','page',
                     'inverter_evidence','transformer_evidence','box_evidence']
    with (out/'alpha15_evidenze.csv').open('w',newline='',encoding='utf-8-sig') as h:
        w=csv.DictWriter(h,fieldnames=evidence_fields,delimiter=';');w.writeheader()
        for r in result['rows']:
            w.writerow({k:','.join(map(str,r[k])) if isinstance(r[k],list) else ('' if r[k] is None else r[k]) for k in evidence_fields})
    # Reuse the unchanged four-sheet Excel template created for Alpha12.
    # The new content is explicitly tagged as alpha15 / documentary staging.
    from .stereotypes_alpha12 import _write_xlsx, _dominant, _qualifier
    records=result['rows']
    by_cu=Counter(r['CU'] for r in result['transformers'])
    by_tr=Counter((r['prefix'],r['CU'],r['TR']) for r in records if r['TR'] is not None)
    tr_model=_dominant([v for v in by_cu.values()])
    inv_model=_dominant([v for v in by_tr.values()])
    detail=[['CU','TR','INV','STR_Box']]; fmt={}
    for idx,row in enumerate(records,2):
        detail.append([row[k] for k in ('CU','TR','INV','STR_Box')])
        cstat=_qualifier(by_cu.get(row['CU']),tr_model)
        istat=_qualifier(by_tr.get((row['prefix'],row['CU'],row['TR'])),inv_model)
        fmt[(idx,2)]=2 if cstat=='STEREOTIPATO' else 3 if cstat=='ECCEZIONE' else 4
        fmt[(idx,3)]=2 if istat=='STEREOTIPATO' else 3 if istat=='ECCEZIONE' else 4
        if row['STR_Box'] is None:fmt[(idx,4)]=4
    sm=result['summary']
    summary=[['Parametro','Valore','Interpretazione'],
      ['Metodo','ALPHA15 - TAG CAD INDICIZZATI','Nessuna Ground Truth usata per inferire'],
      ['CU',sm['cu'],'Rilevate da identificativi in documento'],
      ['TR',sm['tr_candidate'],'Identificativi di trasformatore'],
      ['INV',sm['inverters'],'Identificativi inverter'],
      ['INV con sequenza box completa',sm['box_quantities_complete'],'Serie 1..N senza lacune'],
      ['INV con sequenza box incompleta',sm['box_quantities_unresolved'],'STR_Box lasciato vuoto'],
      ['String Box in sequenze complete',sm['box_quantity_total_complete_only'],'Somma PARZIALE, non totale impianto se incompleto'],
      ['TR per CU prevalente',tr_model,'Verde significa ricorrenza, non continuita verificata'],
      ['INV per TR prevalente',inv_model,'Non assumere numeri fissi'],
      ['Relazioni TR-INV approvate',0,'Da verificare con HITL'],
      ['Matrix FLOW','STAGING','Non e un import certificato']]
    controls=[['CU','TR individuati','INV individuati','INV con SB complete','SB da serie complete','TR per CU','INV per TR','NOTE']]
    for cu in sorted(result['cus']):
        group=[r for r in records if r['CU']==cu]
        tr_counts=[x['TR'] for x in result['transformers'] if x['CU']==cu]
        grouping=[(k[2],v) for k,v in by_tr.items() if k[1]==cu]
        controls.append([cu,len(tr_counts),len(group),sum(r['STR_Box'] is not None for r in group),
                         sum(r['STR_Box'] or 0 for r in group),_qualifier(len(tr_counts),tr_model),
                         '; '.join(f'TR{tr}:{ct}' for tr,ct in sorted(grouping)),
                         'ATTENZIONE: alcune SB da verificare' if any(r['STR_Box'] is None for r in group) else ''])
    evidence=[['CU','TR','INV','STR_Box','Inverter origine','TR candidato','Parent','Quantita SB','Box riconosciute',
               'Serial max','Serial mancanti','Inverter PDF','TR PDF','Box PDF']]
    evfmt={}
    for idx,r in enumerate(records,2):
        evidence.append([r['CU'],r['TR'],r['INV'],r['STR_Box'],r['inv_id'],r['tr_id'],r['parent_status'],r['sb_status'],
                         r['box_ids_observed'],r['box_max_id'],','.join(map(str,r['box_missing_ids'])),
                         r['inverter_evidence'],r['transformer_evidence'],
                         # full provenance retained in alpha15_diagnostica.json
                         r['box_evidence'][:3000]])
        evfmt[(idx,7)]=4  # never verified by tag-family match
        if r['STR_Box'] is None:evfmt[(idx,8)]=3
    path=out/'alpha15_gerarchie_stereotipi.xlsx'
    _write_xlsx(path,[('Dettaglio',detail,[12,12,12,15],fmt),
                      ('Riepilogo',summary,[42,27,95],{}),
                      ('Controlli CU',controls,[12,18,19,23,25,26,37,48],{}),
                      ('Evidenze',evidence,[10,10,10,15,36,35,31,34,18,18,19,78,78,95],evfmt)])
    return out
