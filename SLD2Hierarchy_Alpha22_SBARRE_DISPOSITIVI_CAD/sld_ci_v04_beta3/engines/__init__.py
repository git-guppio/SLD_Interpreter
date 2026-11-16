"""Motori di riconoscimento come plugin + modello dati unico della gerarchia.

Uso tipico::

    from sld_ci_v04_beta3.engines import select_engine
    engine = select_engine(pdf)
    cmd = engine.build_command(pdf, plant_id, out_dir)
    ...
    hierarchy = engine.load_hierarchy(out_dir)
    hierarchy.write(out_dir)      # gerarchia_normalizzata.csv / .json
"""
from .base import DocumentProbe, Recognizer
from .model import Hierarchy, HierarchyRow, Status, read_evidence_csv
from .registry import ENGINES, engine_by_mode, select_engine

__all__ = ['DocumentProbe', 'Recognizer', 'Hierarchy', 'HierarchyRow', 'Status',
           'read_evidence_csv', 'ENGINES', 'engine_by_mode', 'select_engine']
