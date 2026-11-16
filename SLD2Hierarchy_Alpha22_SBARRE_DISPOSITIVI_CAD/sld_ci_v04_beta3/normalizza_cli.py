"""Genera gerarchia_normalizzata.csv/.json per cartelle di output esistenti.

Utile per le esecuzioni precedenti all'introduzione del modello unico:

    python -m sld_ci_v04_beta3.normalizza_cli reports\\sap_alpha16\\PV8\\20261110_101500
    python -m sld_ci_v04_beta3.normalizza_cli --tutte reports\\sap_alpha16
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .engines.registry import engine_for_run


def normalize_run(run_dir: Path) -> str:
    engine = engine_for_run(run_dir)
    if engine is None:
        return f'[SALTATA] {run_dir}: nessun output di motore riconosciuto'
    hierarchy = engine.load_hierarchy(run_dir)
    if not hierarchy.rows:
        return f'[VUOTA]   {run_dir}: {engine.label}, nessuna riga CU/TR/INV'
    hierarchy.write(run_dir)
    s = hierarchy.summary()
    return (f'[OK]      {run_dir}: {engine.label}, inverter={s["righe_inverter"]}, '
            f'parent confermati={s["parent_confermati_operatore"]}, proposti={s["parent_proposti"]}')


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Gerarchia normalizzata da output di motore esistenti')
    p.add_argument('cartelle', nargs='+', type=Path)
    p.add_argument('--tutte', action='store_true',
                   help='cerca ricorsivamente le cartelle di esecuzione sotto quelle indicate')
    a = p.parse_args(argv)
    runs = []
    for folder in a.cartelle:
        if a.tutte:
            runs.extend(sorted({f.parent for f in folder.rglob('*') if f.is_file()
                                and engine_for_run(f.parent) is not None}))
        else:
            runs.append(folder)
    if not runs:
        p.exit(1, 'Nessuna cartella di esecuzione trovata.\n')
    for run in runs:
        try:
            print(normalize_run(run))
        except (OSError, ValueError) as exc:
            print(f'[ERRORE]  {run}: {exc}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
