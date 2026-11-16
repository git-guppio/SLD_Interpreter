"""I quattro motori di riconoscimento attuali, come plugin del registro.

I motori veri e propri restano nei moduli ``sap/*`` e nelle rispettive CLI:
qui si dichiara solo come riconoscerli, lanciarli e leggerne gli output.
"""
from __future__ import annotations

from pathlib import Path
import sys

from .base import DocumentProbe, Recognizer


class LabelFirstRecognizer(Recognizer):
    """Etichette native di posizione (stile PV11): Alpha10-12 + review Alpha13."""
    mode = 'alpha12'
    label = 'Etichette native (Alpha 12)'
    cli_module = 'sld_ci_v04_beta3.sap_stereotypes_cli'
    evidence_csv = 'alpha12_evidenze.csv'
    summary_json = 'alpha12_riepilogo.json'

    def matches(self, probe: DocumentProbe) -> bool:
        return True  # motore di ripiego: si applica sempre

    def build_command(self, pdf: Path, plant_id: str, out_dir: Path,
                      review: Path | None = None, *, executable: str | None = None) -> list[str]:
        # La CLI Alpha12 ha argomenti diversi; riusa il costruttore validato del picker.
        from ..sap_picker_gui import build_export_command
        return build_export_command(pdf, plant_id, out_dir, review, executable=executable)


class IndexedTagRecognizer(Recognizer):
    """Tag indicizzati XX-TR-n-n / XX-INV-n-n (stile PV5/6/7): Alpha15."""
    mode = 'alpha15-indexed'
    label = 'Tag indicizzati (Alpha 15)'
    cli_module = 'sld_ci_v04_beta3.alpha15_cli'
    evidence_csv = 'alpha15_evidenze.csv'
    summary_json = 'alpha15_diagnostica.json'

    def matches(self, probe: DocumentProbe) -> bool:
        from ..sap.multistyle_alpha15 import TR_RE, INV_RE
        return bool(TR_RE.search(probe.text)) and bool(INV_RE.search(probe.text))

    def build_command(self, pdf, plant_id, out_dir, review=None, *, executable=None):
        return super().build_command(pdf, plant_id, out_dir, None, executable=executable)


class LvlRecognizer(Recognizer):
    """Etichette LVL-SB.x.y.z-INV.a.b (stile PV8): Alpha16."""
    mode = 'alpha16-lvl'
    label = 'Famiglia LVL-SB (Alpha 16)'
    cli_module = 'sld_ci_v04_beta3.alpha16_cli'
    evidence_csv = 'alpha16_evidenze.csv'
    summary_json = 'alpha16_diagnostica.json'

    def matches(self, probe: DocumentProbe) -> bool:
        return probe.has_lvl_family

    def build_command(self, pdf, plant_id, out_dir, review=None, *, executable=None):
        return super().build_command(pdf, plant_id, out_dir, None, executable=executable)


class CadVectorRecognizer(Recognizer):
    """CAD solo vettoriale, senza testo nativo (Settimo/PV3): Alpha17-22.

    Il ``mode`` resta 'alpha21-cad' per compatibilita con test e riepiloghi,
    ma la CLI eseguita e quella Alpha22 (superset di Alpha21).
    """
    mode = 'alpha21-cad'
    label = 'CAD vettoriale senza testo (Alpha 22)'
    cli_module = 'sld_ci_v04_beta3.alpha22_cli'
    # La gerarchia esiste solo con review operatore valida (file alpha21_*).
    evidence_csv = 'alpha21_evidenze.csv'
    summary_json = 'alpha21_diagnostica_qps.json'

    def matches(self, probe: DocumentProbe) -> bool:
        return probe.is_vector_only


__all__ = ['LabelFirstRecognizer', 'IndexedTagRecognizer', 'LvlRecognizer', 'CadVectorRecognizer']
