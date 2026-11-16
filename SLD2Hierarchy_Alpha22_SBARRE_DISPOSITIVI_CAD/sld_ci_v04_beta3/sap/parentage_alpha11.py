"""Alpha11: conservative, PDF-only, document-local TR -> central inverter proposals.

A proposal is a *spatial association* consistent with the drawn hierarchy,
not an electrically verified conductor path or a SAP-confirmed parent.
The separate Alpha10 review API remains the only route to confirmation.
There is NO import of any GT/reference data here.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

SCHEMA = 'sld-sap-alpha11-tr-inverter-proposals/v1'
DRAFT_SCHEMA = 'sld-sap-alpha10-reviewed-parentage/v1'


def _scope_number(asset_id: str, kind: str):
    match = re.search(r'::' + re.escape(kind) + r'::(\d+)(?:\.(\d+))?$', asset_id)
    return (int(match.group(1)), int(match.group(2)) if match.group(2) else None) if match else None


def _coords(asset):
    try:
        x, y = float(asset['x']), float(asset['y'])
        return (x, y) if all(math.isfinite(c) for c in (x, y)) else None
    except (TypeError, ValueError, KeyError):
        return None


def propose_parentage(report: dict):
    """Generate proposals without assigning actual parent_id or reading ground truth.

    Pampa's rotated native CAD labels have transformer and inverter rows separated
    in the *text extraction coordinate system*. Candidate rule uses the ordered
    upstream position in the same CU, strictly bounded distances and same-page
    consistency. No fixed number of inverter children is assumed.
    """
    nodes = report.get('assets', [])
    plant_id = report.get('plant_id', '')
    groups = defaultdict(lambda: {'trs': [], 'inv': []})
    for row in nodes:
        typ = row.get('type')
        if typ == 'MV_LV_TRANSFORMER':
            key = row.get('parent_id')
            if key:
                groups[key]['trs'].append(row)
        elif typ == 'CENTRAL_INVERTER' and not row.get('parent_id'):
            key = row.get('cu_context_id')
            if key:
                groups[key]['inv'].append(row)
    candidate_rows=[]
    unresolved=[]
    for cu in sorted(groups):
        tr_rows=groups[cu]['trs']; inv_rows=groups[cu]['inv']
        if not inv_rows:
            continue
        # One CU's candidates must belong to one same PDF page: do not mix
        # another sheet's type symbol or a look-alike from another CU.
        tr_by_page=defaultdict(list)
        for t in tr_rows:
            tr_by_page[t.get('page')].append(t)
        for inv in sorted(inv_rows, key=lambda v:v['asset_id']):
            unresolved_reason = None
            possible = []
            pos = _coords(inv)
            same = [t for t in tr_by_page.get(inv.get('page'), []) if _coords(t) is not None]
            if not same or pos is None:
                unresolved_reason='NO_SAME_PAGE_TR_LABEL_OR_COORDINATES'
            elif len({(round(_coords(t)[0],1), round(_coords(t)[1],1)) for t in same}) != len(same):
                unresolved_reason='OVERLAPPING_TRANSFORMER_LABEL_POSITIONS'
            else:
                xs=sorted([_coords(t)[0] for t in same], reverse=True)
                inv_xs=sorted([_coords(a)[0] for a in inv_rows if a.get('page')==inv.get('page') and _coords(a) is not None],reverse=True)
                tr_pitch=min((abs(a-b) for a,b in zip(xs,xs[1:])),default=0)
                inv_pitch=min((abs(a-b) for a,b in zip(inv_xs,inv_xs[1:])),default=0)
                # Bounded by local device pitch, rather than guessed fanout.
                # One TR may have >2 inverters; distance may grow accordingly.
                max_forward=max(100.0, 2.25*tr_pitch, (len(inv_xs)+0.1)*inv_pitch)
                for tr in same:
                    tx,ty=_coords(tr); ix,iy=pos
                    forward=tx-ix
                    transverse=iy-ty
                    if 3 <= forward <= max_forward and 35 <= transverse <= 260:
                        possible.append((forward,tr))
                possible.sort(key=lambda r:r[0])
                if not possible:
                    unresolved_reason='NO_BOUNDED_UPSTREAM_TR_CANDIDATE'
                elif len(possible)>1 and possible[1][0]-possible[0][0] < 6:
                    unresolved_reason='COMPETING_UPSTREAM_TRANSFORMERS'
            if unresolved_reason:
                unresolved.append({'cu_id':cu,'inverter_id':inv['asset_id'],'reason':unresolved_reason})
                continue
            gap,tr=possible[0]
            trs=_scope_number(tr['asset_id'],'TR'); ids=_scope_number(inv['asset_id'],'INV')
            if not trs or not ids or trs[0]!=ids[0]:
                unresolved.append({'cu_id':cu,'inverter_id':inv['asset_id'],'reason':'INCONSISTENT_ASSET_SCOPE'})
                continue
            conflicted = 'CONFLICT' in inv.get('source_status','')
            candidate_rows.append({
                'cu_id':cu,'inverter_id':inv['asset_id'],
                'proposed_transformer_id':tr['asset_id'],
                'cu_number':ids[0],'inverter_slot':ids[1],
                'transformer_slot':trs[1],
                'source_page':inv['page'],
                'inverter_xy':list(pos),'transformer_xy':list(_coords(tr)),
                'forward_distance':round(gap,2),
                'evidence_basis':'SAME_PAGE_NATIVE_LABELS_BOUNDED_UPSTREAM_SPATIAL_ORDER',
                'evidence_ref':f"{inv.get('evidence_ref','')} | {tr.get('evidence_ref','')}",
                'has_printed_label_conflict':conflicted,
                'status':'REVIEW_REQUIRED_LABEL_CONFLICT' if conflicted else 'SPATIAL_PARENT_CANDIDATE_UNVERIFIED',
                'electrical_continuity_verified':False,
                'sap_parent_confirmed':False,
            })
    # Group repeated patterns as *suggested* HITL actions. Explicit CU
    # membership only; no wildcard, no assertion that examples represent all.
    by_transformer=defaultdict(lambda:defaultdict(set))
    conflicts=defaultdict(bool)
    for c in candidate_rows:
        key=(c['cu_number'],c['transformer_slot'])
        by_transformer[c['cu_number']][c['transformer_slot']].add(c['inverter_slot'])
        if c['has_printed_label_conflict']:
            conflicts[key]=True
    bulk=defaultdict(list)
    for cu,rows in by_transformer.items():
        for tr, inv_slots in rows.items():
            bulk[(tr,tuple(sorted(inv_slots)),conflicts[(cu,tr)])].append(cu)
    suggestion_groups=[]
    for (tr, slots, label_conflict), cu_ids in sorted(bulk.items(),key=lambda kv:(kv[0][0],kv[0][1],kv[0][2])):
        suggestion_groups.append({'transformer_slot':tr,'inverter_slots':list(slots),
                                  'cu_ids':sorted(cu_ids),'number_of_cus':len(cu_ids),
                                  'status':'SUGGESTED_NOT_CONFIRMED',
                                  'evidence_basis':'CONSISTENT_DOCUMENT_LOCAL_SPATIAL_CANDIDATES',
                                  'operator_confirmation_required':True,
                                  'printed_label_conflict_present':label_conflict})
    inv_total=len([a for a in nodes if a.get('type')=='CENTRAL_INVERTER'])
    confirmed=sum(bool(a.get('parent_id')) for a in nodes if a.get('type')=='CENTRAL_INVERTER')
    return {
        'schema':SCHEMA,'plant_id':plant_id,
        'source_pdf':report.get('source_pdf'),
        'candidates':candidate_rows,'unresolved':unresolved,
        'suggested_hitl_groups':suggestion_groups,
        'summary':{'inverters_total':inv_total,
                   'inverters_already_confirmed':confirmed,
                   'spatial_parent_candidates':len(candidate_rows),
                   'spatial_parent_unresolved':len(unresolved),
                   'electrical_paths_verified':0,
                   'parents_auto_confirmed_by_alpha11':0},
        'data_policy':'Candidates only. No GT ingestion, no physical path proof, no automatic SAP parent promotion.'
    }


def make_draft(proposals):
    """Never silently turn suggestions into confirmed HITL assignments."""
    return {
      'schema':DRAFT_SCHEMA,'plant_id':proposals['plant_id'],
      'confirmed_tr_inverter_groups':[], 'confirmed_assets':[],
      'alpha11_suggestions_not_confirmed':proposals['suggested_hitl_groups'],
      'instructions':('Controllare graficamente il pattern in ogni CU elencata; '
                      'trasferire SOLO i gruppi verificati in confirmed_tr_inverter_groups '
                      'con evidence_ref riferito alla verifica. '
                      'Le proposte non sono connettivita elettrica dimostrata.')
    }


def write_proposals(proposals:dict, out_dir:str|Path):
    p=Path(out_dir);p.mkdir(parents=True,exist_ok=True)
    (p/'alpha11_parent_proposals.json').write_text(json.dumps(proposals,ensure_ascii=False,indent=2),encoding='utf-8')
    (p/'alpha11_operator_review_DRAFT.json').write_text(json.dumps(make_draft(proposals),ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['cu_id','inverter_id','proposed_transformer_id','source_page',
          'inverter_slot','transformer_slot','status','has_printed_label_conflict','evidence_ref']
    with (p/'alpha11_parent_proposals.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=cols,delimiter=';');writer.writeheader()
        for row in proposals['candidates']:writer.writerow({c:row.get(c,'') for c in cols})
    with (p/'alpha11_review_suggested_groups.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['transformer_slot','inverter_slots','cu_ids','number_of_cus','status'])
        for row in proposals['suggested_hitl_groups']:
            w.writerow([row['transformer_slot'],','.join(map(str,row['inverter_slots'])),
                        ','.join(map(str,row['cu_ids'])),row['number_of_cus'],row['status']])
    with (p/'alpha11_unresolved.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['cu_id','inverter_id','reason'],delimiter=';');w.writeheader();w.writerows(proposals['unresolved'])
    return p


def build_explicit_review(proposals:dict, approved_groups:list[tuple[int,str]]):
    """Convert *explicitly approved* group indices to Alpha10's scoped review.

    Indices are one-based. No default approval and no wildcard CU scope.
    This function is called by a dedicated interactive operator CLI, never
    from candidate generation.
    """
    if proposals.get('schema') != SCHEMA:
        raise ValueError('Invalid Alpha11 proposal schema')
    suggestions=proposals.get('suggested_hitl_groups',[])
    approved=[];seen=set()
    for number,ev in approved_groups:
        if not isinstance(number,int) or not 1 <= number <= len(suggestions) or number in seen:
            raise ValueError('Duplicate or invalid group index')
        if not isinstance(ev,str) or not ev.strip():
            raise ValueError('Operator evidence_ref required')
        seen.add(number)
        group=suggestions[number-1]
        if not group.get('cu_ids') or not group.get('inverter_slots'):
            raise ValueError('Empty group cannot be approved')
        # Every approved relation must be precisely one proposed edge.
        candidates={(p['cu_number'],p['transformer_slot'],p['inverter_slot'])
                    for p in proposals.get('candidates',[])}
        for cu in group['cu_ids']:
            for inv in group['inverter_slots']:
                if (cu,group['transformer_slot'],inv) not in candidates:
                    raise ValueError('The group is not fully covered by inspected candidate edges')
        approved.append({'cu_ids':list(group['cu_ids']),
                         'transformer_slot':group['transformer_slot'],
                         'inverter_slots':list(group['inverter_slots']),
                         'evidence_ref':ev.strip()})
    review={'schema':DRAFT_SCHEMA,'plant_id':proposals['plant_id'],
            'confirmed_tr_inverter_groups':approved,'confirmed_assets':[],
            'alpha11_approval_note':'Confirmed only for the explicitly listed CUs by the operator; no other rows auto-confirmed.'}
    return review
