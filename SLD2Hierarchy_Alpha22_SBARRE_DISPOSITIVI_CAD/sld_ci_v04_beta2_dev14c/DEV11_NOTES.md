# beta2-dev11 — operator-assisted feeder graph calibration

## Purpose
Dev11 keeps dev10 source-explicit CU→feeder membership unchanged and adds a narrowly scoped human-in-the-loop layer for **electrical graph verification**.

The operator never re-enters CU membership. Operator input can only calibrate the electrical path:

1. `BIND_FEEDER_ROOT_PATTERN` — bind a repeated MV feeder label to its actual graph start/root;
2. `BIND_XFR_MV_TERMINAL_PATTERN` — bind repeated `XFR_n` labels to the MV-side graph terminal;
3. `ADD_FEEDER_GRAPH_BRIDGE_INSTANCE` — confirm one exact missing conductive connection at a trace breakpoint;
4. `ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN` — optional plant-scoped repeated conductive-gap pattern, restricted to XFR terminal neighborhoods.

Transformer windings must never be bridged as conductive graph gaps.

## Provenance
All direct operator input remains `OPERATOR_PROVIDED`.
Reusable geometric patterns are stored with scope `PLANT` only. Exact graph bridges remain current-document feedback and are not generalized.

## Regression policy
Without operator feedback/patterns, dev11 preserves dev10 behavior.

## Tests
37 unit tests pass, including all dev3–dev10 regressions and new dev11 tests for:
- operator feedback contract;
- plant-scoped learning;
- feeder-root binding;
- XFR MV-terminal binding;
- exact graph bridge;
- repeated conductive-gap bridge;
- synthetic end-to-end operator-calibrated graph verification;
- no-feedback dev10 compatibility.

## PV4 workflow
Use the existing dev10 blind result as the first analysis file:

```powershell
python -m sld_ci_v04_beta2_dev11.operator_feeder `
  --sld "..\data\CASE_004_PV4\input\PV4_SLD.pdf" `
  --analysis "..\data\CASE_004_PV4\output\PV4_dev10_blind.json" `
  --feedback "..\data\CASE_004_PV4\output\PV4_feeder_feedback.json"
```

Recommended first calibration on `MV-01`:
1. `BIND_FEEDER_ROOT_PATTERN`: click the actual electrical start of MV-01 at the substation/breaker side, not the text label.
2. `BIND_XFR_MV_TERMINAL_PATTERN`: choose a representative XFR (for example XFR_01) and click its MV-side connection to the collection feeder.

Then run dev11 with feedback:

```powershell
python -m sld_ci_v04_beta2_dev11.cli `
  --sld "..\data\CASE_004_PV4\input\PV4_SLD.pdf" `
  --layout "..\data\CASE_004_PV4\input\PV4_LAYOUT.pdf" `
  --out "..\data\CASE_004_PV4\output\PV4_dev11_assisted.json" `
  --knowledge-store ".\sld_ci_v04_beta2_dev11\knowledge\knowledge_store.json" `
  --operator-feedback "..\data\CASE_004_PV4\output\PV4_feeder_feedback.json"
```

The rerun emits `suggested_breakpoints` per feeder when the graph remains interrupted. Re-open `operator_feeder` using `PV4_dev11_assisted.json`; in `ADD_FEEDER_GRAPH_BRIDGE_INSTANCE` mode the GUI highlights the first suggested pair of endpoints. The operator confirms only if both endpoints are visibly part of the same conductive path.
