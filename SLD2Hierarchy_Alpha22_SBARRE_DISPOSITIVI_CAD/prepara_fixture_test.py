# -*- coding: utf-8 -*-
"""Preflight test PDF di sintesi - NON elabora PDF di impianto.

I documenti PDF dei test path_trace sono generati dal progetto. In caso di
estrazione incompleta dello ZIP o sincronizzazione selettiva, questo script
rigenera soltanto i fixture mancanti/corrotti, senza cambiare il motore.
"""
from pathlib import Path
import runpy
import tempfile
import shutil
import sys

FILES = (
    'crossing_without_dot.pdf', 'crossing_with_dot.pdf',
    't_junction.pdf', 'short_terminal_segment.pdf',
    'colored_conductor.pdf', 'dashed_boundary.pdf',
    'device_interposed.pdf', 'short_gap.pdf',
    'thick_busbar.pdf', 'diagonal_conductor.pdf',
    'segment_limit.pdf',
)
ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'sld_ci_v04_beta3' / 'tests' / 'fixtures'
BUILDER = ROOT / 'sld_ci_v04_beta3' / 'tests' / 'fixture_builder.py'

def valid(path):
    if not path.is_file() or path.stat().st_size == 0:
        return False
    import pymupdf
    try:
        with pymupdf.open(str(path)) as pdf:
            return len(pdf) == 1 and not pdf.is_encrypted
    except (OSError, ValueError, RuntimeError):
        return False

def main():
    try:
        missing = [name for name in FILES if not valid(TARGET/name)]
        if not missing:
            print('[OK] Fixture PDF disponibili: 11/11')
            return 0
        print('[FIXTURE] %d PDF di test mancanti o non validi. Rigenerazione locale...' % len(missing))
        if not BUILDER.is_file():
            raise FileNotFoundError('Generatore PDF di prova assente: %s' % BUILDER)
        # Genera in una cartella temporanea: non sovrascrive i PDF validi.
        with tempfile.TemporaryDirectory(prefix='sld_test_fixtures_') as tmp:
            generator = runpy.run_path(str(BUILDER))['generate']
            generator(tmp)
            TARGET.mkdir(parents=True, exist_ok=True)
            for name in missing:
                generated = Path(tmp)/name
                if not valid(generated):
                    raise RuntimeError('Generazione fallita per %s' % name)
                shutil.copyfile(generated, TARGET/name)
        remains = [name for name in FILES if not valid(TARGET/name)]
        if remains:
            raise RuntimeError('Fixture ancora non validi: %s' % ', '.join(remains))
        print('[OK] Fixture PDF ripristinati e verificati: 11/11')
        return 0
    except Exception as exc:
        print('[ERRORE] Preparazione fixture PDF non riuscita: %s' % exc, file=sys.stderr)
        print('Verificare permessi di scrittura, spazio su disco e PyMuPDF.', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
