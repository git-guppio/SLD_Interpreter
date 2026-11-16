"""Alpha16: evidence-bound native-text recognizer for LVL-SB / INV.x.y SLDs.

This parser does not use plant IDs, filenames, Ground Truth counts, or a
fixed transformer-to-inverter ratio to infer assets. A source label
LVL-SB.<cu>.<inverter>.<box>-INV.<cu>.<inverter> gives explicit SB ownership.
TR parent links from drawing-label locations are PROPOSALS only.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

INVERTER = re.compile(r'^\s*Inv\s*\.\s*(\d{1,4})\s*\.\s*(\d{1,4})\s*$', re.I)
BOX = re.compile(r'\bLVL-SB\.(\d{1,4})\.(\d{1,4})\.(\d{1,4})-INV\.(\d{1,4})\.(\d{1,4})\b', re.I)
CU = re.compile(r'\bSubcampo\s+(\d{1,4})\s*\.\s*\(', re.I)
RATING = re.compile(r'(?<!\d)(\d{2,6}(?:[.,]\d+)?)\s*kVA\b', re.I)
VOLTAGE = re.compile(r'(?<!\d)\d{1,3}(?:[.,]\d{1,3})?\s*/\s*\d{1,3}(?:[.,]\d{1,3})?\s*kV\b', re.I)


def _at(pdf: Path, page_no: int, label: str, pos) -> str:
    return f'{pdf.name}:p{page_no}:{label}:xy=({pos[0]:.2f},{pos[1]:.2f})'


def _lines(page):
    for block in page.get_text('dict').get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            text = ''.join(span.get('text', '') for span in line.get('spans', []))
            yield text, line['bbox']


def _center(rect):
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def _transformer_ratings(page):
    """Two independent native labels must agree: rating and voltage ratio.

    A kVA figure in an unrelated table alone cannot create a transformer.
    """
    text = page.get_text('text')
    ratings = list(dict.fromkeys(m.group(0) for m in RATING.finditer(text)))
    ratios = list(dict.fromkeys(m.group(0) for m in VOLTAGE.finditer(text)))
    voltage_centers = [_center(r) for label in ratios for r in page.search_for(label)]
    if not voltage_centers:
        return []
    results = []
    for label in ratings:
        for rect in page.search_for(label):
            xy = _center(rect)
            if min(((xy[0]-v[0])**2 + (xy[1]-v[1])**2)**.5 for v in voltage_centers) > 65:
                continue
            if any(abs(xy[0]-o['xy'][0])<8 and abs(xy[1]-o['xy'][1])<8 for o in results):
                continue
            results.append({'rating':label,'xy':xy})
    return sorted(results, key=lambda r:(r['xy'][0],r['xy'][1]))


def _nearest_parent(xy, transformers):
    """Candidate only; reject close decisions to avoid fabricated hierarchy."""
    if not transformers:
        return None, 'TR_NON_RILEVATO'
    distances = sorted((abs(xy[0]-t['xy'][0]), t['ordinal']) for t in transformers)
    best = distances[0]
    if len(distances)>1 and distances[1][0] - best[0] < max(20.0, .15 * distances[1][0]):
        return None, 'GEOMETRIA_AMBIGUA'
    return best[1], 'CANDIDATO_PER_PROSSIMITA_X_NON_ELETTRICO'


def detect_lvl_family(pdf_path: str | Path, max_pages: int=4) -> bool:
    """Match *both* standalone inverter IDs and explicit SB ownership tags."""
    with pymupdf.open(str(pdf_path)) as doc:
        for page in list(doc)[:max_pages]:
            content=page.get_text('text')
            if BOX.search(content) and any(INVERTER.fullmatch(txt) for txt,_ in _lines(page)):
                return True
    return False


def extract_lvl_indexed(pdf_path, plant_id):
    pdf = Path(pdf_path)
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    plant = str(plant_id).removeprefix('CI::')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', plant):
        raise ValueError('Identificativo impianto non valido')
    invs={}; boxes=defaultdict(dict); trs={}; cus=set(); issues=[]; pages=[]
    with pymupdf.open(pdf) as doc:
        for num,page in enumerate(doc,1):
            content=page.get_text('text')
            page_inverters={}
            page_lines=list(_lines(page))
            indexed_labels={}
            for line_text, line_bbox in page_lines:
                for indexed_match in BOX.finditer(line_text):
                    indexed_labels.setdefault(indexed_match.group(0).upper(),_center(line_bbox))
            header={int(x) for x in CU.findall(content)}
            for txt,bbox in page_lines:
                match=INVERTER.fullmatch(txt)
                if not match:
                    continue
                key=tuple(int(x) for x in match.groups())
                xy=_center(bbox)
                page_inverters.setdefault(key,[]).append({'xy':xy,'label':txt.strip()})
            for key, seen in page_inverters.items():
                if len(seen)!=1:
                    issues.append({'code':'DUPLICATE_INVERTER_LABEL','inverter':key,'page':num})
                    continue
                if key in invs:
                    issues.append({'code':'INVERTER_ON_MULTIPLE_PAGES','inverter':key,'page':num})
                    continue
                invs[key]={'xy':seen[0]['xy'],'page':num,'label':seen[0]['label'],
                           'evidence':_at(pdf,num,seen[0]['label'],seen[0]['xy'])}
                cus.add(key[0])
                if header and key[0] not in header:
                    issues.append({'code':'CU_HEADER_INVERTER_MISMATCH','inverter':key,'header':sorted(header),'page':num})
            ratings=_transformer_ratings(page)
            if page_inverters:
                for ordinal,r in enumerate(ratings,1):
                    trs[(num,ordinal)]={'ordinal':ordinal,'page':num,'xy':r['xy'],
                                        'rating':r['rating'],
                                        'evidence':_at(pdf,num,r['rating'],r['xy'])}
                if not ratings:
                    issues.append({'code':'TRANSFORMER_LABEL_UNRESOLVED','page':num})
            for m in BOX.finditer(content):
                cu,inv,serial,cu2,inv2=(int(x) for x in m.groups())
                if (cu,inv)!=(cu2,inv2):
                    issues.append({'code':'BOX_INVERTER_TAG_CONFLICT','label':m.group(0),'page':num})
                    continue
                key=(cu,inv)
                label=m.group(0)
                pos=indexed_labels.get(label.upper())
                record={'label':label,'page':num,'evidence':_at(pdf,num,label,pos) if pos else f'{pdf.name}:p{num}:{label}'}
                old=boxes[key].get(serial)
                if old and old['label'].upper()!=label.upper():
                    issues.append({'code':'BOX_SERIAL_COLLISION','inverter':key,'serial':serial,'page':num})
                elif old is None:
                    boxes[key][serial]=record
            pages.append({'page':num,'native_chars':len(content),'standalone_inverters':len(page_inverters),
                          'transformer_rating_candidates':len(ratings) if page_inverters else 0})
    rows=[]
    by_parent=defaultdict(list)
    for key, inv in sorted(invs.items()):
        cu,orig_idx=key
        on_page=[v for (page_no,_),v in trs.items() if page_no==inv['page']]
        tr, status=_nearest_parent(inv['xy'],on_page)
        # Do not attach a transformer on pages showing multiple distinct CUs.
        if len({c for (c,_),v in invs.items() if v['page']==inv['page']}) != 1:
            tr=None;status='TR_CU_AMBIGUOUS'
        # No parent if this page's CU label contradicts the index.
        if any(i['code']=='CU_HEADER_INVERTER_MISMATCH' and i['inverter']==key for i in issues):
            tr=None;status='CU_HEADER_INCOERENTE'
        serials=sorted(boxes.get(key,{}))
        missing=sorted(set(range(1,serials[-1]+1))-set(serials)) if serials else []
        if not serials:
            qty=None; sb_status='NESSUNA_STRING_BOX_IDENTIFICATA'
        elif missing:
            qty=None; sb_status='SEQUENZA_BOX_INCOMPLETA'
            issues.append({'code':'BOX_SERIAL_GAP','inverter':key,'missing_serials':missing,
                           'candidate_max':serials[-1]})
        else:
            qty=len(serials);sb_status='IDENTIFICATIVI_BOX_ESPLICITI_1_N'
        transformer=next((t for t in on_page if t['ordinal']==tr),None)
        row={'CU':cu,'TR':tr,'INV':None,'STR_Box':qty,
             'inv_id':inv['label'],'printed_inv_slot':orig_idx,'page':inv['page'],
             'parent_status':status,'sb_status':sb_status,'box_ids_observed':len(serials),
             'box_max_id':serials[-1] if serials else None,'box_missing_ids':missing,
             'inverter_evidence':inv['evidence'],
             'transformer_evidence':transformer['evidence'] if transformer else '',
             'box_evidence':' | '.join(boxes[key][i]['evidence'] for i in serials),
             'tr_id':f'TR_CANDIDATO_{tr}' if tr is not None else None}
        rows.append(row)
        if tr is not None:by_parent[(cu,tr)].append(row)
        else:issues.append({'code':'TR_PARENT_UNRESOLVED','inverter':key,'reason':status})
    for group in by_parent.values():
        for ordinal,row in enumerate(sorted(group,key=lambda r:r['printed_inv_slot']),1):
            row['INV']=ordinal
    rows.sort(key=lambda r:(r['CU'],r['TR'] if r['TR'] is not None else 999999,
                            r['INV'] if r['INV'] is not None else 999999,r['printed_inv_slot']))
    for key in sorted(boxes):
        if key not in invs:
            issues.append({'code':'BOX_WITHOUT_STANDALONE_INVERTER','inverter':key,
                           'box_count':len(boxes[key])})
    transformers=[]
    for (_,ordinal),obj in sorted(trs.items()):
        # A single CU per page is required to give a transformer a CU parent.
        on_page_cus={cu for (cu,_),inv in invs.items() if inv['page']==obj['page']}
        if len(on_page_cus)==1:
            transformers.append({'CU':next(iter(on_page_cus)),'TR':ordinal,**obj})
        else:
            issues.append({'code':'TR_CU_AMBIGUOUS','page':obj['page'],'ordinal':ordinal})
    return {'schema':'sld-sap-lvl-indexed-alpha16/v1','plant_id':'CI::'+plant,'source_pdf':str(pdf),
            'method':'standalone-inverter-tags + explicit LVL-SB ownership + positional TR candidates',
            'pages':pages,'cus':sorted(cus),'transformers':transformers,'rows':rows,'issues':issues,
            'summary':{'cu':len(cus),'tr_candidate':len(transformers),'inverters':len(invs),
                       'box_quantities_complete':sum(r['STR_Box'] is not None for r in rows),
                       'box_quantities_unresolved':sum(r['STR_Box'] is None for r in rows),
                       'box_quantity_total_complete_only':sum(r['STR_Box'] or 0 for r in rows),
                       'parent_candidates':sum(r['TR'] is not None for r in rows),
                       'parent_confirmed':0,'issue_count':len(issues)},
            'validation_status':'NOT_INDEPENDENTLY_VALIDATED',
            'electrical_connections_verified':0,'matrix_flow_import_ready':False}


def write_outputs(result, target):
    out=Path(target);out.mkdir(parents=True,exist_ok=True)
    (out/'alpha16_diagnostica.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    records=result['rows']
    with (out/'alpha16_CU_TR_INV_STR_Box.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['CU','TR','INV','STR_Box'],delimiter=';');w.writeheader()
        for row in records:w.writerow({key:'' if row[key] is None else row[key] for key in w.fieldnames})
    efields=['CU','TR','INV','STR_Box','inv_id','tr_id','parent_status','sb_status','page',
             'inverter_evidence','transformer_evidence','box_evidence']
    with (out/'alpha16_evidenze.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=efields,delimiter=';');w.writeheader()
        for row in records:w.writerow({key:'' if row[key] is None else row[key] for key in efields})
    from .stereotypes_alpha12 import _write_xlsx,_dominant,_qualifier
    by_cu=Counter(tr['CU'] for tr in result['transformers'])
    by_tr=Counter((r['CU'],r['TR']) for r in records if r['TR'] is not None)
    tr_stereotype=_dominant(list(by_cu.values()))
    inv_stereotype=_dominant(list(by_tr.values()))
    detail=[['CU','TR','INV','STR_Box']];colors={}
    for i,row in enumerate(records,2):
        detail.append([row[k] for k in ('CU','TR','INV','STR_Box')])
        st=_qualifier(by_cu.get(row['CU']),tr_stereotype)
        iv=_qualifier(by_tr.get((row['CU'],row['TR'])),inv_stereotype)
        colors[i,2]=2 if st=='STEREOTIPATO' else 3 if st=='ECCEZIONE' else 4
        colors[i,3]=2 if iv=='STEREOTIPATO' else 3 if iv=='ECCEZIONE' else 4
        if row['STR_Box'] is None:colors[i,4]=4
    s=result['summary']
    summary=[['Parametro','Valore','Interpretazione'],
      ['Metodo','ALPHA16: etichette SB->INV + TR geometrici','Perimetrato ai soli inverter centralizzati'],
      ['CU rilevate',s['cu'],'Da nomi inverter / intestazioni, non da Ground Truth'],
      ['TR candidati',s['tr_candidate'],'Identificati da coppia rating + tensione'],
      ['Inverter',s['inverters'],'Da etichette autonome Inv.n.m'],
      ['INV con SB identificabili',s['box_quantities_complete'],'Quantita di ID distinti LVL-SB'],
      ['Totale SB identificate',s['box_quantity_total_complete_only'],'Nessuna stringa confusa per String Box'],
      ['Parent TR->INV proposti',s['parent_candidates'],'SOLO geometria, nessuna continuita verificata'],
      ['TR per CU prevalenti',tr_stereotype,'Verde indica ripetizione, NON verifica elettrica'],
      ['INV per TR prevalenti',inv_stereotype,'Nessuna cardinalita imposta nel motore'],
      ['Stato Matrix FLOW','STAGING','Non e un import SAP/Matrix FLOW certificato']]
    controls=[['CU','TR candidati','INV rilevati','SB complete (INV)','SB identificate','TR per CU','INV per TR','Note']]
    for cu in result['cus']:
        rr=[r for r in records if r['CU']==cu]
        ct=by_cu.get(cu,0)
        invgroups=sorted((tr,n) for (cc,tr),n in by_tr.items() if cc==cu)
        controls.append([cu,ct,len(rr),sum(r['STR_Box'] is not None for r in rr),
                         sum(r['STR_Box'] or 0 for r in rr),_qualifier(ct,tr_stereotype),
                         '; '.join(f'TR{tr}: {n}' for tr,n in invgroups),
                         'Da verificare' if any(r['STR_Box'] is None or r['TR'] is None for r in rr) else 'Parent TR candidati'])
    evidence=[['CU','TR','INV','STR_Box','Etichetta inverter','TR candidato','Parent','Quantita SB',
               'Pagina','Evidenza inverter','Evidenza TR','Evidenza String Box']]
    ecolors={}
    for i,r in enumerate(records,2):
        evidence.append([r[k] for k in efields])
        ecolors[i,7]=4
    _write_xlsx(out/'alpha16_gerarchie_stereotipi.xlsx',[
        ('Dettaglio',detail,[13,13,13,16],colors),
        ('Riepilogo',summary,[34,54,94],{}),
        ('Controlli CU',controls,[12,17,18,23,22,25,35,38],{}),
        ('Evidenze',evidence,[10,10,10,14,28,27,38,37,15,85,85,92],ecolors)])
    return out
