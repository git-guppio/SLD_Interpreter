"""Alpha12: SAP-oriented tabulation with documentary stereotype diagnostics.

INPUTS are Alpha10 source PDF extraction and Alpha11 candidate parentage; NO Ground Truth.
The compact export is a proposal until parent edges are confirmed through scoped HITL.
No two-inverters-per-transformer or fixed SB-count rule is assumed.
All exported Excel files are written with the Python standard library (OOXML ZIP).
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

SCHEMA = 'sld-sap-stereotypes-alpha12/v1'
MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('', MAIN)


def _parse_id(asset_id, kind, count):
    if not isinstance(asset_id, str):
        return None
    # Re-parse with a strict end-anchored numeric suffix, no guessed numbering.
    suffix = asset_id.split('::' + kind + '::')[-1] if ('::' + kind + '::') in asset_id else ''
    parts = suffix.split('.')
    if len(parts) != count or not all(re.fullmatch(r'\d+', p) for p in parts):
        return None
    return tuple(map(int, parts))


def _dominant(values):
    """Return mode only when supported by >=2 scopes and strict majority."""
    xs = [x for x in values if isinstance(x, int) and x > 0]
    if len(xs) < 2:
        return None
    num, occurrences = Counter(xs).most_common(1)[0]
    return num if occurrences >= 2 and occurrences * 2 > len(xs) else None


def _qualifier(count, stereotype):
    if count is None or count <= 0:
        return 'DA_VERIFICARE'
    if stereotype is None:
        return 'NON_STEREOTIPATO'
    return 'STEREOTIPATO' if count == stereotype else 'ECCEZIONE'


def build_stereotype_export(baseline: dict, proposals: dict):
    if not isinstance(baseline, dict) or not isinstance(proposals, dict):
        raise ValueError('Alpha10 e Alpha11 devono essere oggetti JSON')
    if not str(baseline.get('schema','')).startswith('sld-sap-label-first-alpha10/'):
        raise ValueError('Schema Alpha10 non riconosciuto')
    if not str(proposals.get('schema','')).startswith('sld-sap-alpha11-tr-inverter-proposals/'):
        raise ValueError('Schema Alpha11 non riconosciuto')
    plant = baseline.get('plant_id')
    if not plant or plant != proposals.get('plant_id'):
        raise ValueError('Plant ID diverso tra Alpha10 e Alpha11')
    src = proposals.get('source_pdf')
    if src and baseline.get('source_pdf') and str(src) != str(baseline['source_pdf']):
        raise ValueError('PDF sorgente diverso tra Alpha10 e Alpha11')
    assets = baseline.get('assets')
    if not isinstance(assets, list):
        raise ValueError('Lista assets Alpha10 mancante')
    by_id = {}
    for asset in assets:
        aid = asset.get('asset_id')
        if not aid or aid in by_id or not str(aid).startswith(plant+'::'):
            raise ValueError('Asset ID duplicato, non valido o fuori impianto')
        by_id[aid] = asset
    cus = sorted((a for a in assets if a['type']=='CONVERSION_UNIT'),
                 key=lambda a:_parse_id(a['asset_id'],'CU',1) or (999999,))
    trs = [a for a in assets if a['type']=='MV_LV_TRANSFORMER']
    inverters = [a for a in assets if a['type']=='CENTRAL_INVERTER']
    if len({a['asset_id'] for a in inverters}) != len(inverters):
        raise ValueError('Inverter duplicati')
    candidates={}
    for c in proposals.get('candidates',[]):
        aid = c.get('inverter_id')
        if aid in candidates:
            raise ValueError('Due proposte di parent per uno stesso inverter')
        if aid not in by_id or by_id[aid]['type']!='CENTRAL_INVERTER':
            raise ValueError('Proposta relativa a inverter non presente nel PDF')
        proposed = c.get('proposed_transformer_id')
        if proposed not in by_id or by_id[proposed]['type']!='MV_LV_TRANSFORMER':
            raise ValueError('Proposta con trasformatore assente o di tipo errato')
        candidates[aid]=c

    tr_by_cu = defaultdict(list)
    for t in trs:
        ctx = t.get('parent_id')
        if ctx in by_id and by_id[ctx]['type']=='CONVERSION_UNIT':
            tr_by_cu[ctx].append(t)
    sb_by_inv=defaultdict(list)
    for a in assets:
        if a.get('type')=='STRING_BOX_QUANTITY':
            sb_by_inv[a.get('parent_id')].append(a)
    edges = {}
    issues=[]
    for inv in inverters:
        aid=inv['asset_id']
        parent=inv.get('parent_id')
        c=candidates.get(aid)
        if parent:
            if parent not in by_id or by_id[parent]['type']!='MV_LV_TRANSFORMER':
                raise ValueError('Parent confermato non e un TR valido: '+aid)
            state='CONFERMATO_HITL' if inv.get('parentage')=='OPERATOR_CONFIRMED_TR_PARENT' else 'PARENT_ESPLICITO_DA_VERIFICARE'
            ev=inv.get('operator_evidence_ref') or inv.get('evidence_ref','')
            # Safety: Alpha11 accepted free-text evidence even if it cited only
            # CU19 for a bulk approval of 21/22 different CUs. Reject this
            # specific, provable mismatch without trying to parse general prose.
            only_cu = re.search(r'(?i)(?:^|[:;])\s*CU\s*0*(\d+)\s*$',str(ev))
            actual_cu = _parse_id(aid,'INV',2)
            if state=='CONFERMATO_HITL' and only_cu and actual_cu and int(only_cu.group(1)) != actual_cu[0]:
                state='CONFERMA_HITL_SCOPE_DA_VERIFICARE'
                issues.append({'asset_id':aid,'reason':'EVIDENZA_HITL_SOLO_ALTRA_CU',
                               'evidence_ref':ev})
        elif c:
            parent=c['proposed_transformer_id'];state='CANDIDATO_NON_VERIFICATO'
            ev=c.get('evidence_ref','')
        else:
            parent=None;state='PARENT_NON_RISOLTO';ev=''
        inv_ctx = _parse_id(aid,'INV',2)
        tr_ctx = _parse_id(parent,'TR',2) if parent else None
        cu_ref=inv.get('cu_context_id')
        if inv_ctx is None or (cu_ref and _parse_id(cu_ref,'CU',1) != (inv_ctx[0],)):
            raise ValueError('Identita inverter/CU incoerente: '+aid)
        if tr_ctx is not None and tr_ctx[0] != inv_ctx[0]:
            raise ValueError('Parent in altra CU: '+aid)
        qtys=sb_by_inv.get(aid,[])
        good=[x.get('quantity') for x in qtys if type(x.get('quantity')) is int and x['quantity']>0]
        if len(qtys)==1 and len(good)==1:
            q=good[0];qs='QUANTITA_DA_ETICHETTA'
        elif not qtys:
            q=None;qs='QUANTITA_NON_RISOLTA'
        elif len(good)==len(qtys) and len(set(good))==1:
            q=good[0];qs='ETICHETTE_DUPLICATE_DA_VERIFICARE'
        else:
            q=None;qs='ETICHETTE_IN_CONFLITTO_DA_VERIFICARE'
        if q is None or qs != 'QUANTITA_DA_ETICHETTA':
            issues.append({'asset_id':aid,'reason':qs})
        edges[aid]={'parent':parent,'parent_status':state,'parent_evidence':ev,
                    'sb_quantity':q,'sb_status':qs,
                    'sb_evidence':' | '.join(z.get('evidence_ref','') for z in qtys),
                    'printed_label_conflict': bool(c and c.get('has_printed_label_conflict')) or 'CONFLICT' in inv.get('source_status','')}
        if not parent:
            issues.append({'asset_id':aid,'reason':'TR_PARENT_NON_RISOLTO'})
        if edges[aid]['printed_label_conflict']:
            issues.append({'asset_id':aid,'reason':'ETICHETTA_INVERTER_NON_COHERENTE'})

    inv_by_tr=defaultdict(list)
    for inv in inverters:
        p=edges[inv['asset_id']]['parent']
        if p: inv_by_tr[p].append(inv)
    for tr, items in inv_by_tr.items():
        # Inverter numbering restarts at 1 for each TR (sorted by original slot).
        items.sort(key=lambda a:(_parse_id(a['asset_id'],'INV',2) or (999999,999999))[1])
    slot={a['asset_id']:j for invs in inv_by_tr.values() for j,a in enumerate(invs,1)}
    num_tr={cu['asset_id']:len(tr_by_cu.get(cu['asset_id'],[])) or None for cu in cus}
    num_inv={tr['asset_id']:len(inv_by_tr.get(tr['asset_id'],[])) or None for tr in trs}
    stereotype_tr=_dominant(list(num_tr.values()))
    stereotype_inv=_dominant(list(num_inv.values()))
    uniform_tr=stereotype_tr is not None and all(x==stereotype_tr for x in num_tr.values())
    uniform_inv=stereotype_inv is not None and all(x==stereotype_inv for x in num_inv.values())

    detail=[]; evidence=[]
    for inv in sorted(inverters, key=lambda a:_parse_id(a['asset_id'],'INV',2) or (999999,999999)):
        aid=inv['asset_id']; cnum,orig_slot=_parse_id(aid,'INV',2)
        entry=edges[aid];par=entry['parent']; tctx=_parse_id(par,'TR',2) if par else None
        tr_num=tctx[1] if tctx else None; inv_num=slot.get(aid)
        cu_id=next((a['asset_id'] for a in cus if _parse_id(a['asset_id'],'CU',1)==(cnum,)),None)
        tr_st=_qualifier(num_tr.get(cu_id),stereotype_tr)
        inv_st=_qualifier(num_inv.get(par),stereotype_inv) if par else 'DA_VERIFICARE'
        row={'CU':cnum,'TR':tr_num,'INV':inv_num,'STR_Box':entry['sb_quantity'],
             'tr_stereotype_status':tr_st,'inv_stereotype_status':inv_st}
        detail.append(row)
        evidence.append({'CU':cnum,'TR':tr_num,'INV':inv_num,'asset_id_originale':aid,
                         'slot_INV_originale':orig_slot,'STR_Box':entry['sb_quantity'],
                         'stato_parent':entry['parent_status'],'stato_string_box':entry['sb_status'],
                         'stato_stereotipo_TR':tr_st,'stato_stereotipo_INV':inv_st,
                         'conflitto_etichetta':entry['printed_label_conflict'],
                         'evidenza_parent':entry['parent_evidence'],
                         'evidenza_string_box':entry['sb_evidence']})
    control=[]
    for cu in cus:
        cid=cu['asset_id'];n=_parse_id(cid,'CU',1)[0]
        t_list=sorted(tr_by_cu.get(cid,[]),key=lambda t:_parse_id(t['asset_id'],'TR',2) or (999999,999999))
        tr_count=num_tr[cid]
        tr_counts=[num_inv.get(t['asset_id']) for t in t_list]
        control.append({'CU':n,'TR_rilevati':tr_count,'stereotipo_TR_per_CU':stereotype_tr,
                        'stato_TR':_qualifier(tr_count,stereotype_tr),
                        'inverter_associati':sum(x or 0 for x in tr_counts),
                        'INV_per_TR':'; '.join(f'TR{_parse_id(t["asset_id"],"TR",2)[1]}:{num_inv.get(t["asset_id"]) or "?"}' for t in t_list),
                        'stereotipo_INV_per_TR':stereotype_inv,
                        'stato_INV':'STEREOTIPATO' if tr_counts and stereotype_inv is not None and all(x==stereotype_inv for x in tr_counts) else 'ECCEZIONE' if any(x and stereotype_inv is not None and x!=stereotype_inv for x in tr_counts) else 'DA_VERIFICARE'})
    valid_q=sum(1 for r in detail if r['STR_Box'] is not None)
    confirmed=sum(1 for e in edges.values() if e['parent_status']=='CONFERMATO_HITL')
    summary={'cu':len(cus),'tr':len(trs),'inverters':len(inverters),
             'tr_inverter_parent_candidates_or_confirmed':sum(bool(e['parent']) for e in edges.values()),
             'tr_inverter_parent_hitl_confirmed':confirmed,
             'tr_inverter_parent_unresolved':sum(not e['parent'] for e in edges.values()),
             'string_box_quantities_resolved':valid_q,
             'string_box_quantities_unresolved':len(detail)-valid_q,
             'string_box_quantity_total_resolved':sum(r['STR_Box'] or 0 for r in detail),
             'stereotype_tr_per_cu':stereotype_tr,'stereotype_inv_per_tr':stereotype_inv,
             'stereotype_tr_uniform_all_cus':uniform_tr,'stereotype_inv_uniform_all_trs':uniform_inv,
             'stereotype_is_structural_not_electrically_verified':True,
             'matrix_flow_import_ready':False}
    return {'schema':SCHEMA,'plant_id':plant,'source_pdf':baseline.get('source_pdf'),
            'summary':summary,'detail':detail,'controls':control,'evidence':evidence,'issues':issues,
            'policy':'Stato stereotipato = cardinalita prevalente osservata; non conferma elettrica. '
                     'Campi non risolti vuoti, mai zero. GT non letto.'}


def _cell(parent, coord, value, style=0):
    attrs={'r':coord}
    if style:attrs['s']=str(style)
    if value is None or value == '':
        ET.SubElement(parent,'{%s}c'%MAIN,attrs)
        return
    if type(value) is bool:
        value='SI' if value else 'NO'
    if isinstance(value,(int,float)):
        el=ET.SubElement(parent,'{%s}c'%MAIN,attrs)
        ET.SubElement(el,'{%s}v'%MAIN).text=str(value)
    else:
        el=ET.SubElement(parent,'{%s}c'%MAIN,{**attrs,'t':'str'})
        ET.SubElement(el,'{%s}v'%MAIN).text=str(value)


def _col(i):
    s=''
    while i:
        i,r=divmod(i-1,26);s=chr(65+r)+s
    return s


def _sheet_xml(rows, widths, formats=None, auto_filter=True):
    root=ET.Element('{%s}worksheet'%MAIN)
    svs=ET.SubElement(root,'{%s}sheetViews'%MAIN)
    view=ET.SubElement(svs,'{%s}sheetView'%MAIN,{'workbookViewId':'0'})
    ET.SubElement(view,'{%s}pane'%MAIN,{'ySplit':'1','topLeftCell':'A2','activePane':'bottomLeft','state':'frozen'})
    cols=ET.SubElement(root,'{%s}cols'%MAIN)
    for i,width in enumerate(widths,1):
        ET.SubElement(cols,'{%s}col'%MAIN,{'min':str(i),'max':str(i),'width':str(width),'customWidth':'1'})
    data=ET.SubElement(root,'{%s}sheetData'%MAIN)
    for rnum,vals in enumerate(rows,1):
        r=ET.SubElement(data,'{%s}row'%MAIN,{'r':str(rnum),'ht':'22' if rnum==1 else '17','customHeight':'1'})
        for i,v in enumerate(vals,1):
            # Styles defined in bundled artifact_tool-created Excel template.
            style_map={0:0,1:3,2:9,3:13,4:17}
            sty=3 if rnum==1 else style_map.get((formats or {}).get((rnum,i),0),0)
            _cell(r,f'{_col(i)}{rnum}',v,sty)
    if auto_filter and len(rows)>1:
        ET.SubElement(root,'{%s}autoFilter'%MAIN,{'ref':f'A1:{_col(len(widths))}{len(rows)}'})
    ET.SubElement(root,'{%s}pageMargins'%MAIN,{'left':'0.3','right':'0.3','top':'0.5','bottom':'0.5','header':'0.2','footer':'0.2'})
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def _write_xlsx(path, sheets):
    """Populate a verified base workbook created with artifact_tool.

    The shipped artifact_tool-generated template preserves validated Office
    Open XML package metadata and visual cell styles. At Windows runtime
    this uses only Python's standard library: no pip Excel dependency.
    """
    path=Path(path)
    template=Path(__file__).with_name('alpha12_template.xlsx')
    if not template.is_file():
        raise FileNotFoundError('Manca il template Excel integrato: '+str(template))
    replacements={f'xl/worksheets/sheet{i}.xml':_sheet_xml(rows,widths,formats)
                  for i,(_,rows,widths,formats) in enumerate(sheets,1)}
    with ZipFile(template,'r') as source, ZipFile(path,'w',ZIP_DEFLATED) as target:
        for name in source.namelist():
            target.writestr(name, replacements.pop(name,source.read(name)))
        if replacements:
            raise ValueError('Il template Excel non ha tutti i fogli previsti')


def write_stereotype_outputs(result:dict, directory:str|Path):
    if result.get('schema') != SCHEMA:
        raise ValueError('Schema Alpha12 non valido')
    p=Path(directory);p.mkdir(parents=True,exist_ok=True)
    detail=result['detail'];ctrl=result['controls'];evidence=result['evidence'];summ=result['summary']
    out_csv=p/'alpha12_CU_TR_INV_STR_Box.csv'
    with out_csv.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['CU','TR','INV','STR_Box'])
        for r in detail:
            w.writerow([r.get(k) if r.get(k) is not None else '' for k in ('CU','TR','INV','STR_Box')])
    evcols=['CU','TR','INV','asset_id_originale','slot_INV_originale','STR_Box','stato_parent','stato_string_box','stato_stereotipo_TR','stato_stereotipo_INV','conflitto_etichetta','evidenza_parent','evidenza_string_box']
    with (p/'alpha12_evidenze.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=evcols,delimiter=';');w.writeheader()
        for row in evidence:w.writerow({k:row.get(k,'') if row.get(k,'') is not None else '' for k in evcols})
    (p/'alpha12_riepilogo.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    detailrows=[['CU','TR','INV','STR_Box']]+[[r[k] for k in ('CU','TR','INV','STR_Box')] for r in detail]
    detailformats={}
    for i,row in enumerate(detail,2):
        for col,key in [(2,'tr_stereotype_status'),(3,'inv_stereotype_status')]:
            detailformats[(i,col)]= 2 if row[key]=='STEREOTIPATO' else 3 if row[key]=='ECCEZIONE' else 4
        if row['STR_Box'] is None:detailformats[(i,4)]=4
    sumrows=[['METRICA','VALORE','INTERPRETAZIONE'],
        ['Impianto',result['plant_id'],'SLD sorgente; nessun Ground Truth usato'],
        ['Conversion Unit rilevate',summ['cu'],'Etichette/native o conferme esplicite'],
        ['Trasformatori rilevati',summ['tr'],'Candidati documentali; non tutti elettricamente verificati'],
        ['Inverter centralizzati',summ['inverters'],'Una riga nel Dettaglio per inverter'],
        ['Associazioni TR→INV candidate/confermate',summ['tr_inverter_parent_candidates_or_confirmed'],'Comprende proposte geometriche NON confermate'],
        ['Associazioni confermate HITL',summ['tr_inverter_parent_hitl_confirmed'],'Solo conferme registrate da operatore'],
        ['Quantita String Box risolte',summ['string_box_quantities_resolved'],'Etichette quantitative ricavate dal PDF'],
        ['Somma String Box note',summ['string_box_quantity_total_resolved'],'Non e una capacita teorica di targa'],
        ['STR_Box non risolte',summ['string_box_quantities_unresolved'],'Celle vuote nel Dettaglio; non zero'],
        ['TR per CU prevalenti',summ['stereotype_tr_per_cu'] or 'NON DETERMINATO','Verde solo se coincide con il pattern osservato'],
        ['INV per TR prevalenti',summ['stereotype_inv_per_tr'] or 'NON DETERMINATO','INV rinumerati 1..N per ogni trasformatore'],
        ['TR/CU uniformi su tutto impianto','SI' if summ['stereotype_tr_uniform_all_cus'] else 'NO','NO non significa necessariamente assenza di uno stereotipo prevalente'],
        ['INV/TR uniformi su tutto impianto','SI' if summ['stereotype_inv_uniform_all_trs'] else 'NO','I pattern non sono imposti a nuovi impianti'],
        ['VERDE','STEREOTIPATO','Cardinalita ripetuta; NON equivale a parent elettrico confermato'],
        ['ARANCIONE','ECCEZIONE','Cardinalita differente dal pattern prevalente'],
        ['GRIGIO','DA VERIFICARE','Parent o quantita non determinabili o pattern assente'],
        ['MATRIX FLOW','STAGING','Non e ancora il tracciato SAP FL definitivo']]
    controlcols=['CU','TR_rilevati','stereotipo_TR_per_CU','stato_TR','inverter_associati','INV_per_TR','stereotipo_INV_per_TR','stato_INV']
    controlrows=[controlcols]+[[r.get(k) for k in controlcols] for r in ctrl]
    controlformat={}
    for i,r in enumerate(ctrl,2):
        for col,key in [(4,'stato_TR'),(8,'stato_INV')]:
            controlformat[(i,col)]=2 if r[key]=='STEREOTIPATO' else 3 if r[key]=='ECCEZIONE' else 4
    evrows=[evcols]+[[r.get(k) for k in evcols] for r in evidence]
    evformat={}
    for i,r in enumerate(evidence,2):
        if r['stato_parent'] != 'CONFERMATO_HITL':evformat[(i,7)]=4
        if r['stato_string_box']!='QUANTITA_DA_ETICHETTA':evformat[(i,8)]=4
        if r['conflitto_etichetta']:evformat[(i,11)]=3
    out_xlsx=p/'alpha12_gerarchie_stereotipi.xlsx'
    _write_xlsx(out_xlsx,[('Dettaglio',detailrows,[11,11,11,16],detailformats),
                          ('Riepilogo',sumrows,[45,31,86],{}),
                          ('Controlli CU',controlrows,[11,16,23,21,23,35,27,22],controlformat),
                          ('Evidenze',evrows,[10,10,10,44,23,14,35,41,26,26,23,95,95],evformat)])
    return {'csv':out_csv,'excel':out_xlsx,'evidence_csv':p/'alpha12_evidenze.csv','json':p/'alpha12_riepilogo.json'}
