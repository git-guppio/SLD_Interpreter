"""Soglie del motore CAD vettoriale (Alpha22), configurabili per profilo di stile.

I valori di default sono quelli tarati su Settimo/PV3 e coincidono con il
comportamento storico. Un profilo JSON puo sovrascriverne una parte, ad esempio::

    {"bus_max_gap": 22.0, "series_outline_color": [0.0, 0.6, 0.0]}

Le distanze sono in pixel del rendering normalizzato a 1000 px sul lato lungo
della pagina (sistema di coordinate di Alpha20). Le soglie effettive vengono
copiate nel report di audit per rendere ogni risultato riproducibile.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path

Color = tuple[float, float, float]


@dataclass(frozen=True)
class CadBusThresholds:
    # Sbarra comune (identify_common_buses)
    bus_max_gap: float = 19.0               # distanza max sbarra -> morsetto aperto inverter
    bus_min_span: float = 10.0              # lunghezza minima del segmento sbarra
    bus_transverse_tolerance: float = 2.8   # tolleranza laterale sugli estremi della sbarra
    bus_ambiguous_ratio: float = 0.92       # sotto questo margine due sbarre sono ambigue
    # Avvolgimento TR e tratto secondario (match_winding_to_bus)
    winding_max_axis_offset: float = 2.5
    winding_max_wire_gap: float = 19.0
    # Motivi di apparecchiatura in serie (detect_series_apparatus_motifs), RGB 0..1
    series_outline_color: Color = (0.0, 1.0, 0.0)
    series_contact_color: Color = (1.0, 0.0, 1.0)
    # Archi dispositivo (cad_device_edges): i tratti disegnati devono coprire i due
    # spazi residui conduttore->simbolo->conduttore lungo l'asse del ramo.
    device_axis_tolerance: float = 0.6     # scostamento max di un tratto dall'asse
    device_attach_tolerance: float = 0.55  # lacuna max ammessa (= tolleranza capi Alpha20)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: dict) -> 'CadBusThresholds':
        if not isinstance(data, dict):
            raise ValueError('Il profilo soglie deve essere un oggetto JSON')
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known - {'descrizione'})
        if unknown:
            raise ValueError(f'Soglie sconosciute nel profilo: {", ".join(unknown)}')
        values = {}
        for name in known & set(data):
            value = data[name]
            if name.endswith('_color'):
                if (not isinstance(value, (list, tuple)) or len(value) != 3 or
                        not all(type(v) in (int, float) and 0 <= v <= 1 for v in value)):
                    raise ValueError(f'{name}: atteso [r, g, b] con valori fra 0 e 1')
                values[name] = tuple(float(v) for v in value)
            else:
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError(f'{name}: atteso un numero positivo')
                values[name] = float(value)
        if values.get('bus_ambiguous_ratio', 0.5) >= 1:
            raise ValueError('bus_ambiguous_ratio deve essere minore di 1')
        return cls(**values)

    @classmethod
    def load(cls, path: str | Path | None) -> 'CadBusThresholds':
        if path is None:
            return cls()
        return cls.from_mapping(json.loads(Path(path).read_text(encoding='utf-8-sig')))


DEFAULT = CadBusThresholds()
