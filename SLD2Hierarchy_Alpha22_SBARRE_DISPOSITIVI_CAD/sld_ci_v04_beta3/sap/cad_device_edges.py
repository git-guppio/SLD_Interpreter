"""Archi-dispositivo: attraversamento degli apparecchi in serie SOLO su evidenza disegnata.

Alpha22 trova, dentro ogni discontinuita (TR->sbarra, sbarra->inverter), un
simbolo di apparecchiatura in linea ma non lo attraversa. Questo stadio crea un
**arco tipizzato DEVICE** nel grafo quando, e solo quando, tratti realmente
disegnati nel PDF (di qualunque colore, non tratteggiati) coprono senza lacune
i due spazi residui lungo l'asse del ramo:

    capo a monte --[tratti]--> simbolo --[tratti]--> capo a valle

Nessuna distanza viene "saltata" per prossimita: una lacuna maggiore di
``device_attach_tolerance`` lascia il gap aperto (``DEVICE_SYMBOL_NOT_ATTACHED``).

Limiti dichiarati:
- il tipo di apparecchio (interruttore, sezionatore, TA...) NON e classificato;
- lo stato aperto/chiuso NON e noto: un percorso attraverso archi-dispositivo e
  quindi una relazione ``inferred``, mai una continuita elettrica verificata;
- solo rami verticali (come la sbarra orizzontale di Alpha22).
"""
from __future__ import annotations

from .cad_conductor_graph_alpha20 import frame_scale
from .cad_thresholds import CadBusThresholds, DEFAULT as DEFAULT_THRESHOLDS

MOTIF_OK = 'IN_LINE_DEVICE_LIKE_SYMBOL_SOURCE_OBSERVED_UNCLASSIFIED'
EDGE_OK = 'DEVICE_EDGE_SOURCE_CONNECTED_TYPE_UNCLASSIFIED'
PATH_OK = 'PATH_THROUGH_UNCLASSIFIED_DEVICES'


def collect_vertical_strokes(page):
    """Tratti verticali disegnati (qualsiasi colore, non tratteggiati) nel frame comune.

    Ritorna tuple ``(path_index, x, y_top, y_bottom)``.
    """
    scale = frame_scale(page)
    rotation = page.rotation_matrix
    out = []
    for path_id, path in enumerate(page.get_drawings()):
        if path.get('dashes') not in ('[] 0', None):
            continue  # i tratteggi sono collegamenti ausiliari o bordi, non conduttori
        if path.get('color') is None:
            continue  # solo riempimento, nessun tratto
        for item in path.get('items', ()):
            if item[0] != 'l':
                continue
            p, q = item[1] * rotation, item[2] * rotation
            x0, y0, x1, y1 = (float(v) * scale for v in (p.x, p.y, q.x, q.y))
            if abs(x0 - x1) > 0.36:
                continue
            top, bottom = sorted((y0, y1))
            if bottom - top <= 0:
                continue
            out.append((path_id, (x0 + x1) / 2, top, bottom))
    return out


def uncovered_intervals(intervals, lo, hi, tolerance):
    """Parti di [lo, hi] non coperte dagli intervalli, piu lunghe di ``tolerance``."""
    if hi - lo <= tolerance:
        return []
    gaps, cursor = [], lo
    for a, b in sorted(intervals):
        if b <= cursor:
            continue
        if a > cursor:
            gaps.append((cursor, min(a, hi)))
        cursor = max(cursor, b)
        if cursor >= hi:
            break
    if cursor < hi:
        gaps.append((cursor, hi))
    return [(round(a, 3), round(b, 3)) for a, b in gaps if b - a > tolerance]


def _residual(strokes, x, lo, hi, t):
    on_axis = [(pid, top, bottom) for pid, sx, top, bottom in strokes
               if abs(sx - x) <= t.device_axis_tolerance and bottom >= lo and top <= hi]
    holes = uncovered_intervals([(top, bottom) for _, top, bottom in on_axis], lo, hi,
                                t.device_attach_tolerance)
    return holes, sorted({pid for pid, _, _ in on_axis})


def device_edges(strokes, gaps, motifs, thresholds: CadBusThresholds = DEFAULT_THRESHOLDS):
    """Un esito per ogni gap: arco creato oppure motivo per cui resta aperto.

    ``gaps``: output di ``cad_bus_provenance_alpha22.open_gaps``.
    ``motifs``: output di ``detect_series_apparatus_motifs`` per la stessa pagina.
    """
    by_gap = {}
    for m in motifs:
        by_gap.setdefault((m.get('gap_type'), m.get('downstream_entity')), []).append(m)
    results = []
    for kind, entity, x, y_up, y_down in gaps:
        base = {'gap_type': kind, 'downstream_entity': entity, 'axis_x_px': round(x, 3),
                'gap_px': [round(y_up, 3), round(y_down, 3)],
                'device_type_classified': False, 'device_state_known': False}
        found = by_gap.get((kind, entity), [])
        if len(found) != 1 or found[0].get('status') != MOTIF_OK:
            results.append({**base, 'status': 'NO_UNIQUE_DEVICE_SYMBOL_IN_GAP',
                            'device_edge_created': False})
            continue
        motif = found[0]
        sx0, sy0, sx1, sy1 = motif['symbol_bbox_px']
        if not (y_up <= sy0 and sy1 <= y_down):
            results.append({**base, 'status': 'DEVICE_SYMBOL_OUTSIDE_GAP',
                            'device_edge_created': False})
            continue
        holes_up, leads_up = _residual(strokes, x, y_up, sy0, thresholds)
        holes_down, leads_down = _residual(strokes, x, sy1, y_down, thresholds)
        connected = not holes_up and not holes_down
        results.append({**base,
                        'status': EDGE_OK if connected else 'DEVICE_SYMBOL_NOT_ATTACHED',
                        'device_edge_created': connected,
                        'device_outline_source_path_index': motif.get('outline_source_path_index'),
                        'symbol_bbox_px': motif['symbol_bbox_px'],
                        'upstream_lead_source_path_indices': leads_up,
                        'downstream_lead_source_path_indices': leads_down,
                        'uncovered_upstream_px': holes_up,
                        'uncovered_downstream_px': holes_down})
    return results


def cross_check_review(review, alpha21_result, audit_report):
    """Confronta le parentele TR->INV confermate dall'operatore con i percorsi disegnati.

    Non modifica la review ne l'export: produce un esito per riga, utile per
    indirizzare la verifica HITL dove documento e conferma non concordano.

    - SUPPORTATA_DA_PERCORSO: esiste un percorso disegnato fino al TR candidato;
    - SENZA_PERCORSO_AUTOMATICO: il PDF non permette di ricostruirlo (non e un errore);
    - IN_CONFLITTO_CON_PERCORSO: la review assegna TR diversi a inverter che il
      disegno collega allo stesso avvolgimento (o viceversa).
    """
    if not review or not alpha21_result:
        return []
    converter_of = {r['qps_group']: r['converter_candidate_id']
                    for r in alpha21_result.get('qps_sequences', []) if r.get('qps_group') is not None}
    winding_of = {}
    for page in audit_report.get('pages', []):
        for p in page.get('tr_inverter_paths_through_devices', []):
            winding_of[p['converter_candidate_id']] = (page['page'], tuple(p['chain'][0]['source_paths']))
    rows = []
    confirmations = review.get('parent_confirmations', [])
    for a in confirmations:
        converter = converter_of.get(a.get('qps_group'))
        winding = winding_of.get(converter)
        if winding is None:
            status = 'SENZA_PERCORSO_AUTOMATICO'
        else:
            same_winding_trs = {(b['CU'], b['TR']) for b in confirmations
                                if winding_of.get(converter_of.get(b.get('qps_group'))) == winding}
            same_tr_windings = {winding_of.get(converter_of.get(b.get('qps_group')))
                                for b in confirmations if (b['CU'], b['TR']) == (a['CU'], a['TR'])} - {None}
            status = ('SUPPORTATA_DA_PERCORSO' if len(same_winding_trs) == 1 and len(same_tr_windings) == 1
                      else 'IN_CONFLITTO_CON_PERCORSO')
        rows.append({'qps_group': a.get('qps_group'), 'CU': a.get('CU'), 'TR': a.get('TR'),
                     'INV': a.get('INV'), 'converter_candidate_id': converter,
                     'automatic_winding': list(winding[1]) if winding else None, 'status': status})
    return rows


def tr_inverter_paths(audit_record, edges):
    """Percorsi TR -> dispositivo -> sbarra -> dispositivo -> inverter, se tutti gli archi esistono.

    Il risultato e una relazione ``inferred``: gli apparecchi non sono
    classificati e il loro stato aperto/chiuso non e noto.
    """
    bus = audit_record['busbar_evidence'].get('bus')
    tr = audit_record['winding_evidence'].get('transformer')
    if not bus or not tr:
        return []
    connected = {(e['gap_type'], e['downstream_entity']): e for e in edges if e['device_edge_created']}
    tr_edge = connected.get(('TR_SECONDARY_TO_BUSBAR', 'TR_WINDING_CANDIDATE'))
    if tr_edge is None:
        return []
    paths = []
    for member in bus['members']:
        inv = member['converter_candidate_id']
        inv_edge = connected.get(('BUSBAR_TO_INVERTER', inv))
        if inv_edge is None:
            continue
        paths.append({
            'converter_candidate_id': inv,
            'chain': [
                {'element': 'TR_WINDING_PAIR', 'source_paths': tr['winding_pair_source_paths']},
                {'element': 'TR_SECONDARY_WIRE', 'source_stroke': tr['secondary_source_stroke_index']},
                {'element': 'DEVICE', 'source_path': tr_edge['device_outline_source_path_index']},
                {'element': 'BUSBAR', 'source_stroke': bus['source_stroke_index']},
                {'element': 'DEVICE', 'source_path': inv_edge['device_outline_source_path_index']},
                {'element': 'INVERTER_INPUT_LEAD', 'terminal_px': member['upstream_open_terminal_px']},
            ],
            'status': PATH_OK,
            'parent_status': 'inferred',
            'electrical_path_verified': False,
            'reason_not_verified': 'tipo e stato (aperto/chiuso) degli apparecchi non classificati',
        })
    return paths
