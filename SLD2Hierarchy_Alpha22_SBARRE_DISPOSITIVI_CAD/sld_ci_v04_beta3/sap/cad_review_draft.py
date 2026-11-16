"""Bozza della review operatore CAD (schema Alpha21) precompilata dai percorsi disegnati.

Scrivere a mano il JSON di review richiedeva SHA256 del PDF, schema e
appartenenze CU/TR/INV. Qui la bozza viene costruita dagli output di
un'esecuzione Alpha22:

- SHA256 e plant_id dal PDF/esecuzione;
- un'appartenenza per ogni gruppo QPS documentato (INV = numero del gruppo,
  come richiede la convenzione QPS-n-k/N);
- TR proposto dai percorsi disegnati: inverter collegati allo stesso
  avvolgimento -> stesso TR; senza percorso -> TR None (da compilare);
- CU proposta = 1 (NON dedotta dal disegno: va controllata).

La bozza NON e mai una review valida cosi com'e: ``operator_confirmed`` e le
dichiarazioni semantiche restano False finche l'operatore non le conferma.
``finalize_review`` applica le conferme e la valida con lo stesso validatore
usato dalla CLI, cosi un file salvato e certamente accettato.
"""
from __future__ import annotations

import json
from pathlib import Path

from .cad_qps_hierarchy_alpha21 import REVIEW_SCHEMA, source_sha256, validate_operator_review

DRAFT_NAME = 'review_operatore_bozza.json'
QPS_FILE = 'alpha21_diagnostica_qps.json'
AUDIT_FILE = 'alpha22_audit_sbarre_e_discontinuita.json'


def _windings(audit_report):
    """converter_candidate_id -> chiave avvolgimento (pagina, path sorgente)."""
    out = {}
    for page in audit_report.get('pages', []):
        for p in page.get('tr_inverter_paths_through_devices', []):
            out[p['converter_candidate_id']] = (page['page'], tuple(p['chain'][0]['source_paths']))
    return out


def build_review_draft(pdf_path, plant_id, alpha21_result, audit_report):
    if not plant_id.startswith('CI::'):
        plant_id = 'CI::' + plant_id
    windings = _windings(audit_report)
    tr_number = {w: i + 1 for i, w in enumerate(sorted(set(windings.values())))}
    rows = []
    for seq in sorted(alpha21_result.get('qps_sequences', []), key=lambda r: (r.get('qps_group') is None, r.get('qps_group'))):
        group = seq.get('qps_group')
        if group is None or not seq.get('sequence_complete'):
            continue
        winding = windings.get(seq.get('converter_candidate_id'))
        rows.append({'qps_group': group, 'CU': 1,
                     'TR': tr_number.get(winding) if winding else None,
                     'INV': group,
                     '_inverter_grafico': seq.get('converter_candidate_id'),
                     '_fonte_TR': 'PERCORSO_DISEGNATO' if winding else 'DA_COMPILARE',
                     '_fonte_CU': 'PROPOSTA_DA_CONTROLLARE'})
    return {
        'schema': REVIEW_SCHEMA,
        'plant_id': plant_id,
        'source_pdf_sha256': source_sha256(pdf_path),
        'qps_semantic_class': 'STRING_BOX',
        'qps_is_parallel_string_cabinet': False,
        'qps_group_denotes_inverter_number': False,
        'operator_confirmed': False,
        'operator_evidence': '',
        'parent_confirmations': rows,
        '_bozza': {
            'generata_da': 'percorsi Alpha22 + sequenze QPS Alpha21',
            'nota': ('BOZZA: confermare QPS = String Box, la numerazione QPS-n-k/N, '
                     'CU e TR di ogni riga, e indicare il riferimento della verifica.'),
            'gruppi_QPS_incompleti_esclusi': sum(1 for s in alpha21_result.get('qps_sequences', [])
                                                 if not s.get('sequence_complete')),
        },
    }


def finalize_review(draft, *, operator_evidence, confirm_qps_is_string_box,
                    confirm_numbering, rows=None):
    """Applica le conferme esplicite dell'operatore; i campi interni '_' vengono rimossi."""
    review = {k: v for k, v in draft.items() if not k.startswith('_')}
    review['parent_confirmations'] = [
        {k: v for k, v in r.items() if not k.startswith('_')}
        for r in (rows if rows is not None else draft['parent_confirmations'])]
    review['qps_is_parallel_string_cabinet'] = bool(confirm_qps_is_string_box)
    review['qps_group_denotes_inverter_number'] = bool(confirm_numbering)
    review['operator_evidence'] = (operator_evidence or '').strip()
    review['operator_confirmed'] = True
    return review


def validate_against_run(review, pdf_path, run_dir):
    """Stessa validazione della CLI Alpha21/22 (ValueError se non accettabile)."""
    a21 = json.loads((Path(run_dir) / QPS_FILE).read_text(encoding='utf-8-sig'))
    candidates = [None] * int(a21['summary']['converter_candidates'])
    validate_operator_review(review, pdf_path, review.get('plant_id'), a21['qps_sequences'], candidates)
    return True


def draft_for_run(run_dir, pdf_path, plant_id=None):
    """Bozza dagli output di una cartella di esecuzione Alpha22."""
    run_dir = Path(run_dir)
    a21 = json.loads((run_dir / QPS_FILE).read_text(encoding='utf-8-sig'))
    audit = json.loads((run_dir / AUDIT_FILE).read_text(encoding='utf-8-sig'))
    return build_review_draft(pdf_path, plant_id or a21['plant_id'], a21, audit)
