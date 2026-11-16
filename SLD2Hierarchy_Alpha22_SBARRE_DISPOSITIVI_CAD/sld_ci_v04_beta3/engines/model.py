"""Modello dati unico della gerarchia SAP prodotta dai motori di riconoscimento.

Ogni motore scrive i propri CSV di evidenze con colonne e codici di stato
diversi. Questo modulo li riconduce a un'unica struttura con quattro stati
(dalla roadmap del prodotto):

- ``observed``            quantita/relazione letta direttamente dal documento;
- ``inferred``            proposta dal motore (prossimita, codifica, ordine), non verificata;
- ``operator_confirmed``  confermata da una review operatore vincolata al PDF;
- ``unresolved``          non determinata: NON va interpretata come zero o assente.

Il codice di stato originale del motore resta sempre disponibile
(``raw_status``), cosi la normalizzazione non perde informazione.
Un codice sconosciuto viene classificato ``unresolved`` (scelta prudente).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
from pathlib import Path


class Status(str, Enum):
    OBSERVED = 'observed'
    INFERRED = 'inferred'
    OPERATOR_CONFIRMED = 'operator_confirmed'
    UNRESOLVED = 'unresolved'


# Codici di stato del parent TR->INV emessi dai motori Alpha12/15/16/21.
_PARENT_STATUS = {
    'CONFERMATO_HITL': Status.OPERATOR_CONFIRMED,
    'CONFERMATO_DA_OPERATORE_NON_VERIFICA_ELETTRICA': Status.OPERATOR_CONFIRMED,
    'CANDIDATO_NON_VERIFICATO': Status.INFERRED,
    'CANDIDATO_PER_CODIFICA': Status.INFERRED,
    'CANDIDATO_PER_PROSSIMITA_X_NON_ELETTRICO': Status.INFERRED,
    'PARENT_ESPLICITO_DA_VERIFICARE': Status.INFERRED,
    'NON_RISOLTO': Status.UNRESOLVED,
    'PARENT_NON_RISOLTO': Status.UNRESOLVED,
}

# Codici di stato della quantita String Box.
_SB_STATUS = {
    'QUANTITA_DA_ETICHETTA': Status.OBSERVED,
    'SEQUENZA_BOX_COMPLETA_1_N': Status.OBSERVED,
    'IDENTIFICATIVI_BOX_ESPLICITI_1_N': Status.OBSERVED,
    # Conteggio QPS da OCR+geometria, ma l'equivalenza QPS = String Box
    # vale solo grazie alla conferma dell'operatore.
    'CONTEGGIO_QPS_DA_OCR_GEOMETRIA_CON_SEMANTICA_HITL': Status.OPERATOR_CONFIRMED,
    'QUANTITA_NON_RISOLTA': Status.UNRESOLVED,
    'SEQUENZA_BOX_INCOMPLETA': Status.UNRESOLVED,
    'NESSUNA_STRING_BOX_IDENTIFICATA': Status.UNRESOLVED,
    'NESSUN_IDENTIFICATIVO_BOX_RILEVATO': Status.UNRESOLVED,
}


def normalize_parent_status(raw: str | None) -> Status:
    return _PARENT_STATUS.get((raw or '').strip(), Status.UNRESOLVED)


def normalize_sb_status(raw: str | None, quantity: int | None) -> Status:
    if quantity is None:
        return Status.UNRESOLVED
    return _SB_STATUS.get((raw or '').strip(), Status.UNRESOLVED)


@dataclass(frozen=True)
class HierarchyRow:
    """Una riga CU / TR / INV con la sua quantita di String Box."""
    cu: int | None
    tr: int | None
    inv: int | None
    string_boxes: int | None
    parent_status: Status
    string_box_status: Status
    raw_parent_status: str = ''
    raw_string_box_status: str = ''
    source_asset_id: str = ''
    evidence: tuple[str, ...] = ()


@dataclass
class Hierarchy:
    """Gerarchia normalizzata di un'esecuzione di un motore."""
    engine: str
    plant_id: str
    source_pdf: str
    rows: list[HierarchyRow] = field(default_factory=list)

    def summary(self) -> dict:
        def count(attr, status):
            return sum(1 for r in self.rows if getattr(r, attr) is status)
        resolved = [r.string_boxes for r in self.rows if r.string_boxes is not None]
        return {
            'righe_inverter': len(self.rows),
            'CU': len({r.cu for r in self.rows if r.cu is not None}),
            'TR': len({(r.cu, r.tr) for r in self.rows if r.tr is not None}),
            'parent_confermati_operatore': count('parent_status', Status.OPERATOR_CONFIRMED),
            'parent_proposti': count('parent_status', Status.INFERRED),
            'parent_non_risolti': count('parent_status', Status.UNRESOLVED),
            'string_box_totale_risolto': sum(resolved),
            'string_box_non_risolte': sum(1 for r in self.rows if r.string_boxes is None),
        }

    def to_dict(self) -> dict:
        return {
            'schema': SCHEMA, 'engine': self.engine, 'plant_id': self.plant_id,
            'source_pdf': self.source_pdf, 'summary': self.summary(),
            'rows': [{**asdict(r), 'parent_status': r.parent_status.value,
                      'string_box_status': r.string_box_status.value,
                      'evidence': list(r.evidence)} for r in self.rows],
        }

    def write(self, directory: str | Path) -> dict[str, Path]:
        """Scrive gerarchia_normalizzata.csv/.json nella cartella dell'esecuzione."""
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        csv_path, json_path = out / NORMALIZED_CSV, out / NORMALIZED_JSON
        with csv_path.open('w', encoding='utf-8-sig', newline='') as handle:
            w = csv.writer(handle, delimiter=';')
            w.writerow(['CU', 'TR', 'INV', 'STR_Box', 'stato_parent', 'stato_STR_Box',
                        'stato_parent_motore', 'stato_STR_Box_motore', 'id_asset_sorgente'])
            for r in self.rows:
                w.writerow([_blank(r.cu), _blank(r.tr), _blank(r.inv), _blank(r.string_boxes),
                            r.parent_status.value, r.string_box_status.value,
                            r.raw_parent_status, r.raw_string_box_status, r.source_asset_id])
        json_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        return {'csv': csv_path, 'json': json_path}


SCHEMA = 'sld-normalized-hierarchy/v1'
NORMALIZED_CSV = 'gerarchia_normalizzata.csv'
NORMALIZED_JSON = 'gerarchia_normalizzata.json'


def _blank(value):
    return '' if value is None else value


def _int_or_none(value) -> int | None:
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _split_evidence(*values: str | None) -> tuple[str, ...]:
    items = []
    for v in values:
        items.extend(part.strip() for part in (v or '').split(' | ') if part.strip())
    return tuple(items)


def read_evidence_csv(path: str | Path) -> list[HierarchyRow]:
    """Legge un CSV di evidenze di qualunque motore (due formati supportati).

    - formato "stereotipi" (Alpha12/21): stato_parent, stato_string_box, evidenza_*;
    - formato "indicizzato" (Alpha15/16): parent_status, sb_status, *_evidence.
    """
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, delimiter=';')
        columns = set(reader.fieldnames or ())
        if {'stato_parent', 'stato_string_box'} <= columns:
            parent_key, sb_key, id_key = 'stato_parent', 'stato_string_box', 'asset_id_originale'
            evidence_keys = ('evidenza_parent', 'evidenza_string_box')
        elif {'parent_status', 'sb_status'} <= columns:
            parent_key, sb_key, id_key = 'parent_status', 'sb_status', 'inv_id'
            evidence_keys = ('inverter_evidence', 'transformer_evidence', 'box_evidence')
        else:
            raise ValueError(f'Formato CSV di evidenze non riconosciuto: {path}')
        rows = []
        for raw in reader:
            quantity = _int_or_none(raw.get('STR_Box'))
            rows.append(HierarchyRow(
                cu=_int_or_none(raw.get('CU')), tr=_int_or_none(raw.get('TR')),
                inv=_int_or_none(raw.get('INV')), string_boxes=quantity,
                parent_status=normalize_parent_status(raw.get(parent_key)),
                string_box_status=normalize_sb_status(raw.get(sb_key), quantity),
                raw_parent_status=(raw.get(parent_key) or '').strip(),
                raw_string_box_status=(raw.get(sb_key) or '').strip(),
                source_asset_id=(raw.get(id_key) or '').strip(),
                evidence=_split_evidence(*(raw.get(k) for k in evidence_keys)),
            ))
    return rows
