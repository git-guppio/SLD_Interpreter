"""Optional Windows file-picker for Alpha12. The inference/export engine is unchanged.

This module has no effect on the existing command-line interface. It uses only
Python standard-library tkinter and subprocess, never shell command strings.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ENGINE_MODULE = "sld_ci_v04_beta3.sap_stereotypes_cli"


def valid_plant_id(value: str) -> bool:
    """Allow a portable report folder; reject paths, traversal and shell syntax."""
    return bool(value and len(value) <= 100 and all(c.isalnum() or c in "_-" for c in value))


def default_plant_id(pdf: Path) -> str:
    """Derive an editable suggestion without claiming that the ID is verified."""
    stem = pdf.stem
    result = "".join(c if (c.isalnum() or c in "_-") else "_" for c in stem)
    result = result.strip("_- ")[:100]
    return result or "IMPIANTO"


def build_export_command(
    pdf: Path, plant_id: str, out_dir: Path, review_json: Path | None = None,
    executable: str | None = None,
) -> list[str]:
    """Build a safe argument vector: spaces/accents in file paths stay intact."""
    if not valid_plant_id(plant_id):
        raise ValueError("ID impianto non valido: usa lettere, numeri, trattino o underscore.")
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise ValueError("Seleziona un file PDF esistente.")
    if review_json is not None and (not review_json.is_file() or review_json.suffix.lower() != ".json"):
        raise ValueError("Seleziona un JSON HITL esistente oppure non usarne alcuno.")
    cmd = [
        executable or sys.executable, "-m", ENGINE_MODULE,
        "--sld", str(pdf), "--plant-id", plant_id, "--out-dir", str(out_dir),
    ]
    if review_json is not None:
        cmd.extend(["--review-json", str(review_json)])
    return cmd


def _initial_dir(project_root: Path) -> Path:
    for folder in (project_root / "data", Path.home() / "Documents", Path.home()):
        if folder.is_dir():
            return folder
    return project_root


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog
    except ImportError:
        print("[ERRORE] Tkinter non disponibile. Usa il file strumenti\\esporta_gerarchia_stereotipi_PDF.bat (modalita manuale).")
        return 3

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update_idletasks()
    except tk.TclError as ex:
        print(f"[ERRORE] Impossibile aprire la finestra di selezione: {ex}")
        print("Alternativa: strumenti\\esporta_gerarchia_stereotipi_PDF.bat (modalita manuale).")
        return 3

    project_root = Path(__file__).resolve().parent.parent
    try:
        pdf_file = filedialog.askopenfilename(
            parent=root,
            title="Alpha 12 - Seleziona lo schema unifilare (PDF)",
            initialdir=str(_initial_dir(project_root)),
            filetypes=[("Schemi PDF", "*.pdf"), ("Tutti i file", "*.*")],
        )
        if not pdf_file:
            print("[ANNULLATO] Nessun PDF selezionato: non e stato elaborato nulla.")
            return 0
        pdf = Path(pdf_file)
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            messagebox.showerror("File non valido", "Seleziona un documento PDF esistente.", parent=root)
            return 2

        plant_id = simpledialog.askstring(
            "Identificativo impianto",
            "Conferma o modifica l'identificativo dell'impianto.\n"
            "Verra usato nella cartella dei risultati:",
            initialvalue=default_plant_id(pdf), parent=root,
        )
        if plant_id is None:
            print("[ANNULLATO] Nessuna modifica effettuata.")
            return 0
        plant_id = plant_id.strip()
        if not valid_plant_id(plant_id):
            messagebox.showerror(
                "Identificativo non valido",
                "Usa solo lettere, numeri, trattini e underscore (senza spazi).",
                parent=root,
            )
            return 2

        use_review = messagebox.askyesno(
            "Conferme HITL (facoltative)",
            "Vuoi caricare un JSON HITL gia approvato?\n\n"
            "Per la prima prova scegli NO.\n"
            "Se scegli SI, seleziona il file JSON dalla finestra successiva.\n\n"
            "Attenzione: usa solo revisioni che confermano le CU effettivamente verificate.",
            default=messagebox.NO, parent=root,
        )
        review: Path | None = None
        if use_review:
            json_file = filedialog.askopenfilename(
                parent=root,
                title="Alpha 12 - Seleziona il JSON HITL approvato",
                initialdir=str(project_root / "reports") if (project_root / "reports").is_dir() else str(pdf.parent),
                filetypes=[("File JSON", "*.json"), ("Tutti i file", "*.*")],
            )
            if not json_file:
                print("[ANNULLATO] Nessun JSON HITL selezionato: non e stato elaborato nulla.")
                return 0
            review = Path(json_file)

        out_dir = project_root / "reports" / "sap_alpha12" / plant_id
        existing_files = [out_dir / name for name in (
            "alpha12_CU_TR_INV_STR_Box.csv", "alpha12_gerarchie_stereotipi.xlsx",
            "alpha12_evidenze.csv", "alpha12_riepilogo.json",
        )]
        if any(file.exists() for file in existing_files):
            if not messagebox.askyesno(
                "Risultati esistenti",
                f"Esistono gia risultati Alpha 12 per {plant_id}.\n\n"
                "Vuoi sostituire i report di questo impianto?\n"
                "Il PDF originale e il JSON HITL non verranno modificati.",
                default=messagebox.NO, parent=root,
            ):
                print("[ANNULLATO] Report esistenti conservati, nessuna esportazione.")
                return 0

        try:
            cmd = build_export_command(pdf, plant_id, out_dir, review)
        except ValueError as ex:
            messagebox.showerror("Parametri non validi", str(ex), parent=root)
            return 2

        print("\n--- ALPHA 12 | AVVIO CON SELEZIONE FILE ---", flush=True)
        print("PDF:", pdf, flush=True)
        print("Impianto:", plant_id, flush=True)
        print("JSON HITL:", str(review) if review else "nessuno", flush=True)
        print("Report:", out_dir, flush=True)
        print("\nAnalisi in corso: i risultati saranno mostrati qui sotto.\n", flush=True)
        try:
            outcome = subprocess.run(cmd, cwd=project_root, check=False)
        except OSError as ex:
            messagebox.showerror("Avvio non riuscito", str(ex), parent=root)
            return 2

        if outcome.returncode:
            messagebox.showerror(
                "Esportazione non riuscita",
                "L'elaborazione non e riuscita.\n"
                "Controlla il messaggio di errore nella finestra PowerShell.\n"
                "Il PDF originale non e stato modificato.",
                parent=root,
            )
            return outcome.returncode

        print("\n[OK] Esportazione completata:", out_dir, flush=True)
        if messagebox.askyesno(
            "Esportazione completata",
            f"Excel e CSV generati in:\n{out_dir}\n\nVuoi aprire la cartella dei risultati?",
            parent=root,
        ):
            if sys.platform == "win32":
                try:
                    os.startfile(str(out_dir))
                except OSError as ex:
                    print(f"Impossibile aprire la cartella automaticamente: {ex}")
            else:
                print("Cartella report:", out_dir)
        if messagebox.askyesno(
            "Alpha 13 - Verifica visiva delle evidenze",
            "Vuoi aprire il verificatore visivo per controllare inverter, TR e String Box?\n\n"
            "Potrai confermare soltanto i singoli inverter ispezionati.\n"
            "Le segnalazioni da correggere non cambiano l analisi automaticamente.",
            default=messagebox.NO, parent=root,
        ):
            try:
                from .sap_visual_review_gui import run_viewer
                run_viewer(root, out_dir / "alpha12_riepilogo.json", pdf, out_dir)
            except (ValueError, OSError, RuntimeError, KeyError) as ex:
                messagebox.showerror("Verifica visiva non avviata", str(ex), parent=root)
                print("[ERRORE] Alpha13 visual review:", ex)
        return 0
    finally:
        root.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
