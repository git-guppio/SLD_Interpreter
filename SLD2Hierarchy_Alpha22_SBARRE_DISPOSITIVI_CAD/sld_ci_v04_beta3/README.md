# SLD2Hierarchy — beta3 / bootstrap 1

**State:** geometry research baseline, NOT yet an end-to-end replacement for beta2.

## Contents

- `sld_ci_v04_beta2_dev14c/`: frozen original source, not edited.
- `sld_ci_v04_beta3/geometry/kernel.py`: new separate vector connectivity prototype.
- `sld_ci_v04_beta3/tests/`: 11 real, generated, vector PDF fixture tests.
- `sld_ci_v04_beta3/regression/oracle.json`: scoring-only expected values, never accessed by inference.
- `sld_ci_v04_beta3/regression/score.py`: post-run diagnostic.
- `run_tests.bat`: Windows launch of independent beta3 PDF tests + beta2 existing tests.

## Prerequisites
Python 3.11+; packages: pymupdf networkx (legacy beta2 additionally needs its documented dependencies).
Install: `python -m pip install pymupdf networkx`

## Tests from package parent
`python -m unittest discover -s sld_ci_v04_beta3/tests -t . -v`
`python -m unittest discover -s sld_ci_v04_beta2_dev14c/tests -t . -v`

## Produce PDF fixtures
`python -m sld_ci_v04_beta3 --create-fixtures fixtures`

## Geometry study on a real page (diagnostic, no asset interpretation)
`python -m sld_ci_v04_beta3 --pdf "..\data\CASE_004_PV4\input\PV4_SLD.pdf" --page 1 --out "..\data\CASE_004_PV4\output\beta3_geometry_page1.json"`

## Continue existing stable runs with unchanged beta2 dev14c
`python -m sld_ci_v04_beta2_dev14c.workflow --case "..\data\CASE_004_PV4"`

## Post-run benchmark (requires matching complete legacy output)
`python -m sld_ci_v04_beta3.regression.score --case CASE_004_PV4 --output "..\data\CASE_004_PV4\output\PV4_dev14b.json"`

This score is counts-only and cannot prove end-to-end physical graph correctness.

## Restrictions
- Beta3 runtime does not read `regression/oracle.json`, GT, or historical expected counts.
- No PV4/PV8-specific runtime geometry rules.
- No silent line-bridging.
- No code nor outputs generated in any CASE by default; output path explicit.
- The vector graph is an isolated research kernel and is NOT integrated into the legacy `workflow.py` until regression gates pass.
- Dash style exclusion is a baseline candidate behavior; future iteration must distinguish conductor style from non-electrical drafting.
- Algorithm complexity is currently O(n²); do NOT run directly on very large SLD pages without spatial indexing, layers and bound handling.
- Junction dot recognition uses PDF filled-circle shape; raster-only PDF remains unsupported by this experimental module.

## Alpha 5: multistyle diagnostic preflight

`python -m sld_ci_v04_beta3.multistyle_cli --pdf path/to/plant.pdf --plant-id PLANT`

Per documenti con riferimenti diversi dai rimandi reciproci PV8, il modulo
`integration.multistyle` classifica matchlines, riferimenti documentali, tag di
apparecchiature elettriche sul medesimo foglio e assenza di testo nativo.
Quando esistono tag locali puo' selezionare regioni di verifica geometrica,
con identificativi dei tratti vettoriali e limiti espliciti. Preview OCR solo
con flag `--ocr-preview` e Tesseract disponibile. Nessun collegamento elettrico
viene promosso automaticamente. Vedere `LEGGIMI_ALPHA5.md` nella root.
