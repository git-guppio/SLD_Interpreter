# beta2_dev4 checkpoint

## Why dev4
PV8 showed that the CLI raw candidate summary can be mistaken for final asset counts.
The resolved target hierarchy was already 55 CU / 220 inverter / 1320 String Box, while
raw candidate types reported much larger intermediate values.

## Changes
- Separate `analysis_counts` (raw/intermediate) from `target_counts` (resolved hierarchy).
- Add apparent-power (`kVA` / `MVA`) semantic evidence as `RATING`; this does not auto-classify equipment.
- If power-rating evidence exists but no transformer is resolved, emit a visual transformer-resolution request.
- Visual hints can display the rating text that motivated the request.
- Target counts are always derived only from resolved hierarchical membership.
- No Ground Truth is used by inference.

## Intended PV8 behavior
- target_counts: 55 CU, 220 inverter, 1320 String Box from explicit semantic hierarchy.
- transformer rating evidence: unresolved; visual/operator path is opened rather than returning a false zero as a confident result.
