"""Registro dei motori e scelta del motore per un PDF."""
from __future__ import annotations

from pathlib import Path

from .base import DocumentProbe, Recognizer
from .recognizers import (CadVectorRecognizer, IndexedTagRecognizer,
                          LabelFirstRecognizer, LvlRecognizer)

FALLBACK = LabelFirstRecognizer()

#: Ordine di valutazione: il primo motore che riconosce il documento vince.
#: L'ordine replica il dispatch storico del workbench. Il motore di ripiego
#: (etichette native) e sempre l'ultimo.
ENGINES: tuple[Recognizer, ...] = (
    IndexedTagRecognizer(),
    LvlRecognizer(),
    CadVectorRecognizer(),
    FALLBACK,
)


def engine_by_mode(mode: str) -> Recognizer:
    for engine in ENGINES:
        if engine.mode == mode:
            return engine
    raise KeyError(f'Motore sconosciuto: {mode}')


def engine_for_run(run_dir: str | Path) -> Recognizer | None:
    """Motore che ha prodotto una cartella di output, dai file presenti."""
    run_dir = Path(run_dir)
    for engine in ENGINES:
        if (run_dir / engine.summary_json).is_file() or (run_dir / engine.evidence_csv).is_file():
            return engine
    return None


def select_engine(pdf_path: str | Path, review=None) -> Recognizer:
    """Sceglie il motore in base alle evidenze del documento.

    Una review Alpha13 vale solo per la pipeline a etichette native che l'ha
    prodotta, quindi la sua presenza forza quel motore.
    """
    if review is not None:
        return FALLBACK
    probe = DocumentProbe(pdf_path)
    return next(engine for engine in ENGINES if engine.matches(probe))
