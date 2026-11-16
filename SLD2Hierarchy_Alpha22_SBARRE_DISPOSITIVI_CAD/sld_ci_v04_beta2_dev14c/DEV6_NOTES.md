# beta2_dev7 checkpoint

## Purpose

`dev6` formalizes a multi-source case model:

- `PVx_SLD.pdf` = primary source for equipment, hierarchy and target counts;
- `PVx_LAYOUT.pdf` = optional auxiliary source for plant overview, MV-line topology and CU distribution.

The layout is useful when present, but it is never a prerequisite for interpreting the SLD.
No rule assumes that the first page is an overview.

## Main rules

1. **SLD and layout are processed as separate source documents.**
2. **Only SLD pages enter the physical-equipment acceptance/classification pipeline.**
   Layout content therefore cannot inflate inverter, transformer or string-box counts.
3. **CU identity is reconciled across sources by explicit instance identity.**
   A CU appearing in both sources becomes one canonical plant-level CU.
4. **Layout-only CU identities are retained**, because the layout may legitimately expose plant structure missing from the SLD overview.
5. **CU -> MV line membership is conservative.**
   Automatic membership requires:
   - an explicit MV-line / feeder identifier; and
   - the CU label and line identifier to bind to the same electrical graph component.
   Proximity alone does not create membership.
6. Missing layout, missing MV-line labels or ambiguous graph topology remain unresolved rather than guessed.
7. Ground Truth remains excluded from inference.

## New modules

- `source_resolution.py`: filename/case reconciliation and page-role resolution independent of page number.
- `layout_evidence.py`: explicit MV-line / feeder text evidence.
- `layout_resolution.py`: layout CU representations and conservative CU-to-MV-line topology.
- `source_reconciliation.py`: canonical CU identity across SLD and layout.

## CLI

Recommended multi-source mode:

```powershell
python -m sld_ci_v04_beta2_dev10.cli `
  --sld "..\data\CASE_008_PV8\input\PV8_SLD.pdf" `
  --layout "..\data\CASE_008_PV8\input\PV8_LAYOUT.pdf" `
  --out "..\data\CASE_008_PV8\output\PV8_dev6.json" `
  --knowledge-store ".\sld_ci_v04_beta2_dev10\knowledge\knowledge_store.json"
```

If no layout exists, omit `--layout`:

```powershell
python -m sld_ci_v04_beta2_dev10.cli `
  --sld "..\data\CASE_006_PV6\input\PV6_SLD.pdf" `
  --out "..\data\CASE_006_PV6\output\PV6_dev6.json" `
  --knowledge-store ".\sld_ci_v04_beta2_dev10\knowledge\knowledge_store.json"
```

Legacy `--pdf` remains available as a single-SLD compatibility mode.

## Output additions

- `sources.sld` / `sources.layout`
- `layout_pages`
- `layout_resolution`
- `source_reconciliation`
- source-separated `analysis_counts.sld` / `analysis_counts.layout`

`target_counts` keeps equipment counts derived from the SLD hierarchy.  The CU count is the canonical union of explicit CU identities from the SLD and optional layout, with separate fields showing SLD-only and layout-only coverage.

## Validation

16 unit tests pass: all prior dev3-dev5 tests plus six dev6 multi-source tests.
A two-source smoke test confirmed that adding the same PDF as an auxiliary layout did not change SLD equipment target counts; it only changed cross-source CU coverage.
