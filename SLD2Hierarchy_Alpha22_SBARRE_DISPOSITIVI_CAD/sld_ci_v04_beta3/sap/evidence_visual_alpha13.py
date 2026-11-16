"""Alpha13: read-only PDF evidence preview and strictly per-inverter HITL ledger.

Inferences made by Alpha10/11/12 are not modified by this module.  This is
an operator review of proposed parentage and documentary String Box quantities,
not automatic proof of an electrical circuit.  No ground truth is read.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

try:
    import pymupdf as fitz
except ImportError:
    import fitz

ALPHA12_SCHEMA = 'sld-sap-stereotypes-alpha12/v1'
HITL_SCHEMA = 'sld-sap-alpha10-reviewed-parentage/v1'
LEDGER_FILENAME = 'alpha13_operator_review_APPROVED.json'
LOG_FILENAME = 'alpha13_registro_verifiche.csv'
_REF = re.compile(
    r'(?P<file>.+?):p(?P<page>\d+):(?P<label>.+?):xy=\('
    r'(?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+)),\s*'
    r'(?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\)'
)
_INV_ID = re.compile(r'::INV::(\d+)\.(\d+)$')


def _basename(path: str) -> str:
    return PureWindowsPath(path).name


def parse_evidence_ref(value: str) -> list[dict]:
    """Parse the exact Alpha12 evidence format, without executing any text."""
    if not isinstance(value, str):
        return []
    points = []
    for part in value.split(' | '):
        match = _REF.fullmatch(part.strip())
        if not match:
            continue
        page = int(match['page'])
        x, y = float(match['x']), float(match['y'])
        if page < 1 or not math.isfinite(x) or not math.isfinite(y):
            continue
        points.append({'file': _basename(match['file']), 'page': page,
                       'label': match['label'], 'x': x, 'y': y})
    return points


def load_evidence(report_json: str | Path, pdf_path: str | Path) -> tuple[dict,list[dict]]:
    """Validate identity/scope of the generated report and chosen source PDF."""
    path = Path(report_json)
    pdf = Path(pdf_path)
    if not path.is_file() or not pdf.is_file() or pdf.suffix.lower() != '.pdf':
        raise ValueError('Servono sia un report Alpha12 JSON sia il PDF originale.')
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    if report.get('schema') != ALPHA12_SCHEMA or not report.get('plant_id'):
        raise ValueError('Il report selezionato non e un riepilogo Alpha12 valido.')
    if _basename(str(report.get('source_pdf', ''))).lower() != pdf.name.lower():
        raise ValueError('Il PDF non corrisponde al documento sorgente del report Alpha12.')
    records = report.get('evidence')
    if not isinstance(records,list):
        raise ValueError('Il report non contiene il registro Evidenze.')
    seen = set()
    for r in records:
        if not isinstance(r, dict):
            raise ValueError('Riga Evidenze malformata.')
        asset = r.get('asset_id_originale')
        if not isinstance(asset,str) or not asset.startswith(report['plant_id']+'::INV::') or not _INV_ID.search(asset):
            raise ValueError('Identificativo inverter non valido o appartenente a un altro impianto.')
        if asset in seen:
            raise ValueError('Doppio inverter nello stesso report: '+asset)
        seen.add(asset)
        if type(r.get('CU')) is not int or r['CU'] < 1:
            raise ValueError('Numero CU non valido.')
        m = _INV_ID.search(asset)
        if int(m[1]) != r['CU'] or int(m[2]) != r.get('slot_INV_originale'):
            raise ValueError('CU o identificativo originale non coerente: '+asset)
    with fitz.open(pdf) as doc:
        for r in records:
            for key in ('evidenza_parent', 'evidenza_string_box'):
                for marker in parse_evidence_ref(r.get(key, '')):
                    if marker['file'].lower() != pdf.name.lower() or marker['page'] > len(doc):
                        raise ValueError('Riferimento PDF incoerente per '+r['asset_id_originale'])
    return report, records


def markers_for_record(record: dict, pdf_name: str) -> list[dict]:
    """Three kinds of document anchors; first parent is INV, second TR."""
    parent = parse_evidence_ref(record.get('evidenza_parent',''))
    sb = parse_evidence_ref(record.get('evidenza_string_box',''))
    markers = []
    if parent:
        markers.append(dict(parent[0], kind='INV'))
    if len(parent)>1:
        markers.append(dict(parent[1], kind='TR'))
    if len(sb)==1:
        markers.append(dict(sb[0], kind='STR_Box'))
    return [p for p in markers if p['file'].lower()==pdf_name.lower()]


def evidence_is_complete(record: dict, pdf_name: str) -> bool:
    """This is an eligibility test for a human review, NOT automatic proof."""
    if not (type(record.get('CU')) is int and type(record.get('TR')) is int and
            type(record.get('INV')) is int and type(record.get('STR_Box')) is int and
            record.get('stato_string_box') == 'QUANTITA_DA_ETICHETTA' and
            record.get('stato_parent') in {'CANDIDATO_NON_VERIFICATO','CONFERMATO_HITL',
                                            'PARENT_ESPLICITO_DA_VERIFICARE'}):
        return False
    markers = markers_for_record(record,pdf_name)
    if {p['kind'] for p in markers} != {'INV','TR','STR_Box'}:
        return False
    return len({p['page'] for p in markers}) == 1


def crop_plan(page, record: dict, pdf_name: str):
    """Map extracted unrotated word coordinates onto the displayed rotated PDF.

    Returns a clip and markers in PAGE DISPLAY coordinates.  The original PDF
    is never annotated or changed.
    """
    source = markers_for_record(record,pdf_name)
    markers=[]
    for p in source:
        if p['page'] != page.number+1:
            continue
        visual = fitz.Point(p['x'],p['y']) * page.rotation_matrix
        if not all(math.isfinite(x) for x in (visual.x,visual.y)):
            continue
        if not page.rect.contains(visual):
            continue
        markers.append(dict(p, vx=visual.x,vy=visual.y))
    if not markers:
        raise ValueError('Nessuna coordinata valida e visualizzabile per questa pagina.')
    minx,maxx=min(p['vx'] for p in markers),max(p['vx'] for p in markers)
    miny,maxy=min(p['vy'] for p in markers),max(p['vy'] for p in markers)
    if maxx-minx > 1350 or maxy-miny > 1200:
        raise ValueError('Le etichette sono troppo lontane per un ritaglio unico: verifica manuale nel PDF.')
    cx=(minx+maxx)/2; cy=(miny+maxy)/2
    width=max(430,maxx-minx+180)
    height=max(340,maxy-miny+150)
    clip=fitz.Rect(cx-width/2,cy-height/2,cx+width/2,cy+height/2) & page.rect
    if clip.is_empty:
        raise ValueError('Area del PDF vuota.')
    return clip,markers


def render_preview(page, record: dict, pdf_name: str,
                   max_width: int=850, max_height: int=590) -> tuple[bytes,list[dict],dict]:
    clip, markers = crop_plan(page,record,pdf_name)
    scale = min(2.5, max_width/clip.width, max_height/clip.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale,scale), clip=clip, alpha=False)
    display=[]
    for m in markers:
        display.append({**m, 'px': (m['vx']-clip.x0)*scale,
                             'py':(m['vy']-clip.y0)*scale})
    return pix.tobytes('png'),display,{'width':pix.width,'height':pix.height,'clip':list(clip),'zoom':scale}


class VisualReviewLedger:
    """Per-inverter reviews, persisted as an Alpha10-compatible HITL JSON.

    Failed checks are audit records only, never corrections to the source or
    hidden parent confirmations.  Reopening requires an exact report/PDF hash.
    """
    def __init__(self, report_path: str|Path, pdf_path: str|Path, output_dir: str|Path):
        self.report_path=Path(report_path)
        self.pdf_path=Path(pdf_path)
        self.output_dir=Path(output_dir)
        self.report,self.records=load_evidence(self.report_path,self.pdf_path)
        self.by_id={r['asset_id_originale']:r for r in self.records}
        self.report_sha256=hashlib.sha256(self.report_path.read_bytes()).hexdigest()
        self.pdf_sha256=hashlib.sha256(self.pdf_path.read_bytes()).hexdigest()
        self.decisions={}
        self.out_json=self.output_dir/LEDGER_FILENAME
        if self.out_json.exists():
            self._load_existing()

    def _load_existing(self):
        doc=json.loads(self.out_json.read_text(encoding='utf-8-sig'))
        meta=doc.get('alpha13_source',{})
        if (doc.get('schema')!=HITL_SCHEMA or doc.get('plant_id')!=self.report['plant_id'] or
            meta.get('pdf_sha256')!=self.pdf_sha256 or meta.get('report_sha256')!=self.report_sha256):
            raise ValueError('Un JSON HITL Alpha13 esistente appartiene a un altro PDF o a un diverso report. '
                             'Conservalo e scegli una nuova cartella per i risultati.')
        rows=doc.get('alpha13_visual_checks',[])
        if not isinstance(rows,list):
            raise ValueError('Registro HITL esistente danneggiato.')
        for d in rows:
            if not isinstance(d,dict) or d.get('asset_id') not in self.by_id or d.get('status') not in {'CONFERMATO_VISIVO','DA_CORREGGERE'}:
                raise ValueError('Registro HITL contiene controlli non validi o di un altro impianto.')
            if d['asset_id'] in self.decisions:
                raise ValueError('Registro HITL contiene verifiche duplicate.')
            self.decisions[d['asset_id']]=d

    def set_decision(self, asset_id: str, status: str, notes: str = ''):
        if asset_id not in self.by_id:
            raise ValueError('Inverter non presente nel report.')
        if status not in {'CONFERMATO_VISIVO','DA_CORREGGERE'}:
            raise ValueError('Esito non valido.')
        r=self.by_id[asset_id]
        if status == 'CONFERMATO_VISIVO' and not evidence_is_complete(r,self.pdf_path.name):
            raise ValueError('Evidenze incomplete: impossibile confermare insieme parent e String Box.')
        if status=='DA_CORREGGERE' and not notes.strip():
            raise ValueError('Descrivi cosa va corretto; nessuna correzione automatica.')
        self.decisions[asset_id]={
            'asset_id':asset_id,'status':status,'CU':r['CU'],'TR':r.get('TR'),
            'INV':r.get('INV'),'slot_INV_originale':r['slot_INV_originale'],
            'STR_Box':r.get('STR_Box'),'stato_parent_originale':r.get('stato_parent'),
            'stato_string_box_originale':r.get('stato_string_box'),
            'page':parse_evidence_ref(r.get('evidenza_parent',''))[0]['page'] if parse_evidence_ref(r.get('evidenza_parent','')) else None,
            'notes':notes.strip(),'reviewed_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'basis':'OPERATOR_VISUAL_REVIEW_NOT_ELECTRICAL_PATH_PROOF',
        }
        self.save()

    def clear_decision(self,asset_id:str):
        if asset_id in self.decisions:
            del self.decisions[asset_id]
            self.save()

    def make_hitl(self):
        confirmed=[]
        for r in self.records:
            aid=r['asset_id_originale']; check=self.decisions.get(aid)
            if not check or check['status']!='CONFERMATO_VISIVO':
                continue
            if not evidence_is_complete(r,self.pdf_path.name):
                raise ValueError('Conferma non giustificata da evidenze: '+aid)
            # One exact CU and original PDF inverter slot per review.
            p=parse_evidence_ref(r['evidenza_parent'])[0]
            confirmed.append({
                'cu_ids':[r['CU']],'transformer_slot':r['TR'],
                'inverter_slots':[r['slot_INV_originale']],
                'evidence_ref':f'ALPHA13_VISUAL:{self.pdf_path.name}:p{p["page"]}:CU{r["CU"]}:TR{r["TR"]}:I{r["slot_INV_originale"]}',
            })
        return {
            'schema':HITL_SCHEMA,'plant_id':self.report['plant_id'],
            'confirmed_tr_inverter_groups':confirmed,'confirmed_assets':[],
            'alpha13_source':{'pdf_filename':self.pdf_path.name,'pdf_sha256':self.pdf_sha256,
                              'report_sha256':self.report_sha256},
            'alpha13_visual_checks':[self.decisions[r['asset_id_originale']]
                                     for r in self.records if r['asset_id_originale'] in self.decisions],
            'alpha13_note':('Verifica individuale: conferma dell operatore, non continuita elettrica dimostrata. '
                            'Le quantita SB verificate sono registrate in alpha13_visual_checks. '
                            'Le righe DA_CORREGGERE non alterano automaticamente i conteggi o i parent.'),
        }

    def save(self):
        self.output_dir.mkdir(parents=True,exist_ok=True)
        data=self.make_hitl()
        tmp=self.out_json.with_suffix('.json.tmp')
        try:
            tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
            os.replace(tmp,self.out_json)
        finally:
            if tmp.exists():tmp.unlink()
        with (self.output_dir/LOG_FILENAME).open('w',encoding='utf-8-sig',newline='') as f:
            cols=['CU','TR','INV','STR_Box','asset_id','status','page','notes','reviewed_at_utc']
            writer=csv.DictWriter(f,fieldnames=cols,delimiter=';');writer.writeheader()
            for c in data['alpha13_visual_checks']:
                writer.writerow({k:c.get(k,'') for k in cols})
        return self.out_json
