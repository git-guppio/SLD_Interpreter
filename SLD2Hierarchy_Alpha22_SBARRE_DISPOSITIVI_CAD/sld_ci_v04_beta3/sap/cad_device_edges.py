"""Archi-dispositivo: attraversamento degli apparecchi in serie SOLO su evidenza disegnata.

Alpha22 trova, dentro ogni discontinuita (TR->sbarra, sbarra->inverter), un
simbolo di apparecchiatura in linea ma non lo attraversa. Questo stadio crea un
**arco tipizzato DEVICE** nel grafo quando, e solo quando, elementi realmente
disegnati nel PDF coprono senza lacune, lungo l'asse del ramo, i due spazi
residui capo a monte -> simbolo -> capo a valle.

Elementi che coprono un tratto d'asse (qualsiasi colore, mai tratteggiati):

- tratto verticale sull'asse (conduttore o terminale);
- primitive IEC 60617 dell'apparecchio, riconosciute solo se poggiano sull'asse:
  * ``WITHDRAWABLE_CONTACT``: triangolo chiuso con vertice sull'asse e base
    che lo attraversa (contatto di sezionamento / parte estraibile);
  * ``BREAKER_CONTACT_X``: due diagonali incrociate centrate sull'asse
    (funzione interruttore sul contatto fisso);
  * ``SWITCH_BLADE``: lama obliqua con un capo sull'asse e la punta spostata
    lateralmente (contatto mobile, disegnato aperto per convenzione).

Nessuna distanza viene "saltata" per prossimita: una lacuna maggiore di
``device_attach_tolerance`` lascia il gap aperto (``DEVICE_SYMBOL_NOT_ATTACHED``).

Dalle primitive trovate deriva un **tipo candidato** (es. interruttore
estraibile), da confermare: ``device_type_classified`` resta False. Lo stato
aperto/chiuso non e rappresentato nello schema, quindi un percorso attraverso
archi-dispositivo e una relazione ``inferred``, mai continuita verificata.
Solo rami verticali (come la sbarra orizzontale di Alpha22).
"""
from __future__ import annotations

from .cad_conductor_graph_alpha20 import frame_scale
from .cad_thresholds import CadBusThresholds, DEFAULT as DEFAULT_THRESHOLDS

MOTIF_OK = 'IN_LINE_DEVICE_LIKE_SYMBOL_SOURCE_OBSERVED_UNCLASSIFIED'
EDGE_OK = 'DEVICE_EDGE_SOURCE_CONNECTED_TYPE_UNCLASSIFIED'
PATH_OK = 'PATH_THROUGH_UNCLASSIFIED_DEVICES'

_EPS = 0.06  # tolleranza numerica di disegno CAD (vertici "coincidenti")


def _stroked_paths(page):
    """(path_id, [segmenti (x0,y0,x1,y1)]) dei path a tratto pieno, nel frame comune."""
    scale = frame_scale(page)
    rotation = page.rotation_matrix
    for path_id, path in enumerate(page.get_drawings()):
        if path.get('dashes') not in ('[] 0', None):
            continue  # i tratteggi sono collegamenti ausiliari o bordi, non conduttori
        if path.get('color') is None:
            continue  # solo riempimento (es. frecce del comando), nessun tratto
        segments = []
        for item in path.get('items', ()):
            if item[0] != 'l':
                continue
            p, q = item[1] * rotation, item[2] * rotation
            segments.append(tuple(float(v) * scale for v in (p.x, p.y, q.x, q.y)))
        yield path_id, segments


def _triangle(segments, max_size):
    """Triangolo chiuso con base orizzontale: (apice_x, apice_y, base_y, base_x0, base_x1)."""
    if len(segments) != 3:
        return None
    pts = []
    for x0, y0, x1, y1 in segments:
        for p in ((x0, y0), (x1, y1)):
            if not any(abs(p[0] - q[0]) <= _EPS and abs(p[1] - q[1]) <= _EPS for q in pts):
                pts.append(p)
    if len(pts) != 3:
        return None  # non chiuso o degenere
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if max(xs) - min(xs) > max_size or max(ys) - min(ys) > max_size or max(ys) - min(ys) < 0.3:
        return None
    for apex in pts:
        base = [p for p in pts if p is not apex]
        if abs(base[0][1] - base[1][1]) <= _EPS and abs(apex[1] - base[0][1]) >= 0.3:
            bx0, bx1 = sorted((base[0][0], base[1][0]))
            if bx0 < apex[0] < bx1:
                return apex[0], apex[1], base[0][1], bx0, bx1
    return None


def _diagonal(seg, lo, hi):
    x0, y0, x1, y1 = seg
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    return lo <= dx <= hi and lo <= dy <= hi and 0.5 <= dx / dy <= 2.0


def collect_axis_evidence(page, thresholds: CadBusThresholds = DEFAULT_THRESHOLDS):
    """Elementi disegnati che possono coprire un tratto d'asse verticale.

    - ``strokes``: (path_id, x, top, bottom) tratti verticali;
    - ``primitives``: dict(kind, source_path, axis_x, top, bottom) per triangoli e X;
    - ``blades``: dict(source_path, ends=((x,y),(x,y))) segmenti obliqui candidati lama.
    """
    t = thresholds
    strokes, primitives, blades = [], [], []
    for path_id, segments in _stroked_paths(page):
        for x0, y0, x1, y1 in segments:
            if abs(x0 - x1) <= 0.36 and abs(y1 - y0) > 0:
                top, bottom = sorted((y0, y1))
                strokes.append((path_id, (x0 + x1) / 2, top, bottom))
        tri = _triangle(segments, t.device_primitive_max_size)
        if tri:
            ax, ay, by, _, _ = tri
            primitives.append({'kind': 'WITHDRAWABLE_CONTACT', 'source_path': path_id,
                               'axis_x': ax, 'top': min(ay, by), 'bottom': max(ay, by)})
            continue
        diagonals = [s for s in segments if _diagonal(s, 0.3, t.device_primitive_max_size)]
        in_x = set()
        for i, a in enumerate(diagonals):
            for b in diagonals[i + 1:]:
                ba = (min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3]))
                bb = (min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3]))
                slope_a = (a[2] - a[0]) * (a[3] - a[1])
                slope_b = (b[2] - b[0]) * (b[3] - b[1])
                if all(abs(u - v) <= _EPS for u, v in zip(ba, bb)) and slope_a * slope_b < 0:
                    in_x.update((a, b))
                    if any(p['kind'] == 'BREAKER_CONTACT_X' and p['source_path'] == path_id and
                           abs(p['top'] - ba[1]) <= _EPS and abs(p['axis_x'] - (ba[0] + ba[2]) / 2) <= _EPS
                           for p in primitives):
                        continue  # stessa X (segmenti ripetuti nel path)
                    primitives.append({'kind': 'BREAKER_CONTACT_X', 'source_path': path_id,
                                       'axis_x': (ba[0] + ba[2]) / 2, 'top': ba[1], 'bottom': ba[3]})
        for x0, y0, x1, y1 in segments:
            if (x0, y0, x1, y1) in in_x:
                continue
            dx, dy = abs(x1 - x0), abs(y1 - y0)
            if 0.6 <= dx <= t.device_blade_max_offset and dy >= 1.0:
                blades.append({'source_path': path_id, 'ends': ((x0, y0), (x1, y1))})
    return {'strokes': strokes, 'primitives': primitives, 'blades': blades}


def collect_vertical_strokes(page):
    """Solo i tratti verticali (compatibilita): (path_index, x, y_top, y_bottom)."""
    return collect_axis_evidence(page)['strokes']


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


def _residual(evidence, x, lo, hi, t):
    """Copertura di [lo, hi] sull'asse x: (lacune, path dei tratti, primitive usate)."""
    tol = t.device_axis_tolerance

    def overlaps(top, bottom):
        return bottom >= lo and top <= hi

    intervals, leads, components = [], set(), []
    for pid, sx, top, bottom in evidence.get('strokes', ()):
        if abs(sx - x) <= tol and overlaps(top, bottom):
            intervals.append((top, bottom)); leads.add(pid)
    for prim in evidence.get('primitives', ()):
        if abs(prim['axis_x'] - x) <= tol and overlaps(prim['top'], prim['bottom']):
            intervals.append((prim['top'], prim['bottom']))
            components.append({'kind': prim['kind'], 'source_path': prim['source_path']})
    for blade in evidence.get('blades', ()):
        (xa, ya), (xb, yb) = blade['ends']
        # Esattamente un capo sull'asse: la punta e spostata lateralmente.
        if (abs(xa - x) <= tol) != (abs(xb - x) <= tol):
            top, bottom = sorted((ya, yb))
            if overlaps(top, bottom):
                intervals.append((top, bottom))
                components.append({'kind': 'SWITCH_BLADE', 'source_path': blade['source_path']})
    holes = uncovered_intervals(intervals, lo, hi, t.device_attach_tolerance)
    unique = list({(c['kind'], c['source_path']): c for c in components}.values())
    return holes, sorted(leads), unique


def device_type_candidate(kinds):
    """Tipo candidato dalle primitive IEC trovate; None se non deducibile."""
    kinds = set(kinds)
    withdrawable = '_ESTRAIBILE' if 'WITHDRAWABLE_CONTACT' in kinds else ''
    if {'BREAKER_CONTACT_X', 'SWITCH_BLADE'} <= kinds:
        return 'INTERRUTTORE' + withdrawable
    if 'SWITCH_BLADE' in kinds:
        return 'SEZIONATORE_O_IMS' + withdrawable
    return None


def device_edges(evidence, gaps, motifs, thresholds: CadBusThresholds = DEFAULT_THRESHOLDS):
    """Un esito per ogni gap: arco creato oppure motivo per cui resta aperto.

    ``evidence``: output di ``collect_axis_evidence`` (o lista di soli tratti verticali).
    ``gaps``: output di ``cad_bus_provenance_alpha22.open_gaps``.
    ``motifs``: output di ``detect_series_apparatus_motifs`` per la stessa pagina.
    """
    if isinstance(evidence, list):
        evidence = {'strokes': evidence}
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
        holes_up, leads_up, comp_up = _residual(evidence, x, y_up, sy0, thresholds)
        holes_down, leads_down, comp_down = _residual(evidence, x, sy1, y_down, thresholds)
        components = comp_up + comp_down
        connected = not holes_up and not holes_down
        results.append({**base,
                        'status': EDGE_OK if connected else 'DEVICE_SYMBOL_NOT_ATTACHED',
                        'device_edge_created': connected,
                        'device_outline_source_path_index': motif.get('outline_source_path_index'),
                        'symbol_bbox_px': motif['symbol_bbox_px'],
                        'device_components': components,
                        'device_type_candidate': device_type_candidate(c['kind'] for c in components),
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
                {'element': 'DEVICE', 'source_path': tr_edge['device_outline_source_path_index'],
                 'type_candidate': tr_edge.get('device_type_candidate')},
                {'element': 'BUSBAR', 'source_stroke': bus['source_stroke_index']},
                {'element': 'DEVICE', 'source_path': inv_edge['device_outline_source_path_index'],
                 'type_candidate': inv_edge.get('device_type_candidate')},
                {'element': 'INVERTER_INPUT_LEAD', 'terminal_px': member['upstream_open_terminal_px']},
            ],
            'status': PATH_OK,
            'parent_status': 'inferred',
            'electrical_path_verified': False,
            'reason_not_verified': ('stato aperto/chiuso non rappresentato nello schema; '
                                    'tipo apparecchio solo candidato (primitive IEC 60617), da confermare'),
        })
    return paths
