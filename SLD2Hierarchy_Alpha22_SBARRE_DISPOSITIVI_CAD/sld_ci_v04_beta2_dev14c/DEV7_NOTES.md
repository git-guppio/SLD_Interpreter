# beta2-dev7 — structural MV feeder recovery from optional layout

## Why
PV8 validates the SLD/layout split, but its layout PDF has a corrupt native text encoding for the eight visible feeder labels. The drawing visibly contains `LINEA 1` … `LINEA 8`, while native extraction returns mojibake/control characters. dev6 therefore reported `mv_line_count = 0` despite a valid layout.

## Rule
Direct readable line identifiers remain authoritative. When they are unavailable, dev7 may recover *structural feeder trunks* from repeated long vertical vector conductors in a plant-layout source. This fallback does **not** claim to decode the source label.

Recovered lines therefore use:
- `source_status = INFERRED`
- a synthetic grouping key such as `LAYOUT_FEEDER_01`
- `label_status = UNRESOLVED`

CU membership may be inferred only when the CU is unambiguously aligned to one structurally recovered feeder relative to the feeder spacing. Generic proximity alone is still insufficient.

## PV8 standalone layout verification
Using `PV8_LAYOUT.pdf` only:
- 55 CU representations detected
- 8 structural feeder candidates recovered
- 55/55 CU-to-feeder memberships resolved structurally
- 0 unresolved CU memberships
- 8 feeder source labels remain unresolved because the PDF text layer is corrupt

The recovered column grouping is:
- LAYOUT_FEEDER_01: CU 7,6,5,4,1,2,3
- LAYOUT_FEEDER_02: CU 14,13,12,8,9,10,11
- LAYOUT_FEEDER_03: CU 15,19,20,18,17,21,16
- LAYOUT_FEEDER_04: CU 22,23,24,25,28,27,26
- LAYOUT_FEEDER_05: CU 29,30,31,35,34,33,32
- LAYOUT_FEEDER_06: CU 36,40,41,39,42,38,37
- LAYOUT_FEEDER_07: CU 43,44,45,46,47,48,49
- LAYOUT_FEEDER_08: CU 50,51,52,53,55,54

These are topology groups, not yet asserted source labels `LINEA 1..8`.

## Tests
18 unit tests pass, including all dev3–dev6 regressions plus two dev7 feeder-recovery tests.
