"""Interfaccia comune dei motori di riconoscimento e sonda del documento."""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import cached_property
from itertools import islice
import json
from pathlib import Path
import sys

from .model import Hierarchy, read_evidence_csv


class DocumentProbe:
    """Caratteristiche del PDF usate per scegliere il motore.

    Ogni proprieta e calcolata solo quando serve e una sola volta, cosi la
    scelta non riapre il PDF piu del necessario.
    """

    PAGES = 3  # come il dispatch storico: solo le prime tre pagine

    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)

    @cached_property
    def text(self) -> str:
        try:
            import pymupdf
        except ImportError:  # pragma: no cover - vecchie installazioni
            import fitz as pymupdf
        with pymupdf.open(str(self.pdf_path)) as doc:
            return '\n'.join(page.get_text('text') for page in islice(doc, self.PAGES))

    @cached_property
    def has_lvl_family(self) -> bool:
        from ..sap.lvl_indexed_alpha16 import detect_lvl_family
        return bool(detect_lvl_family(self.pdf_path))

    @cached_property
    def is_vector_only(self) -> bool:
        from ..sap.vector_diagnostics_alpha17 import vector_only_document
        return bool(vector_only_document(self.pdf_path))


class Recognizer(ABC):
    """Un motore di riconoscimento per una famiglia di stili di SLD.

    Per aggiungere uno stile: sottoclasse + registrazione in ``registry.ENGINES``.
    """

    #: identificativo stabile (usato in log, test e riepiloghi; non cambiarlo)
    mode: str
    #: descrizione per l'operatore
    label: str
    #: modulo CLI eseguito in un processo separato
    cli_module: str
    #: CSV di evidenze scritto dal motore nella cartella di output
    evidence_csv: str
    #: JSON di riepilogo scritto dal motore (plant_id, source_pdf, summary)
    summary_json: str

    @abstractmethod
    def matches(self, probe: DocumentProbe) -> bool:
        """True se il documento presenta le evidenze di questo stile."""

    def build_command(self, pdf: Path, plant_id: str, out_dir: Path,
                      review: Path | None = None, *, executable: str | None = None) -> list[str]:
        cmd = [executable or sys.executable, '-m', self.cli_module,
               '--pdf', str(pdf), '--plant-id', plant_id, '--out', str(out_dir)]
        if review is not None:
            cmd.extend(['--review-json', str(review)])
        return cmd

    def read_summary(self, out_dir: Path) -> dict | None:
        path = Path(out_dir) / self.summary_json
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8-sig'))

    def load_hierarchy(self, out_dir: Path) -> Hierarchy:
        """Gerarchia normalizzata dagli output; vuota se il motore non l'ha prodotta."""
        out_dir = Path(out_dir)
        summary = self.read_summary(out_dir) or {}
        hierarchy = Hierarchy(engine=self.mode, plant_id=str(summary.get('plant_id', '')),
                              source_pdf=str(summary.get('source_pdf', '')))
        evidence = out_dir / self.evidence_csv
        if evidence.is_file():
            hierarchy.rows = read_evidence_csv(evidence)
        return hierarchy
