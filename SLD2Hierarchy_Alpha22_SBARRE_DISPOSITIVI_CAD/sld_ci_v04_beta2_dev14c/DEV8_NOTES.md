# beta2-dev8 — Operator resolution of MV feeder labels

This checkpoint closes the Human-in-the-Loop loop introduced by dev7 for plant-layout MV feeders.

## What dev8 adds

- One grouped `MV_LINE_LABEL_MAPPING` resolution request when structural MV feeders are recovered but their native PDF labels remain unreadable.
- `operator_layout.py`, a console helper that lists the unresolved synthetic feeders and the CU instances already assigned to each feeder, then asks the operator for the actual source labels.
- Operator feedback keeps `status=OPERATOR_PROVIDED` and is stored separately from automatic topology inference.
- The CU→feeder relation remains `INFERRED`; only the feeder label provenance becomes `OPERATOR_PROVIDED` (or `LEARNED_OPERATOR_PATTERN` on later runs).
- The learned mapping is deliberately `PLANT` scoped. It can suppress repeated questions when the same plant is re-run, but it is never applied to another plant.
- Direct readable source line labels still have precedence over operator/learned mappings.

## Safety / anti-assumption rule

Dev8 does **not** assume that left-to-right feeder order equals LINEA 1..N. The operator must provide the labels. Structural ordering is only a deterministic way to present the unresolved feeders.

## Workflow

1. Run dev8 normally on SLD + optional LAYOUT.
2. If `OPEN LAYOUT RESOLUTION REQUESTS` contains `MV_LINE_LABEL_MAPPING`, run:

```powershell
python -m sld_ci_v04_beta2_dev10.operator_layout `
  --analysis "..\data\CASE_008_PV8\output\PV8_dev8.json" `
  --feedback "..\data\CASE_008_PV8\output\PV8_layout_feedback.json"
```

3. Enter the actual line labels in the displayed feeder order, separated by `|`.
4. Re-run dev8 with `--operator-feedback` pointing to the saved feedback JSON.
5. With a knowledge store enabled, the mapping is retained for subsequent runs of the same plant.

## PV8 real-layout smoke test

Before operator input, the uploaded PV8 layout yields:
- 55 CU representations
- 8 structural MV feeder candidates
- 55 resolved CU→feeder memberships
- 8 unresolved feeder labels

Applying an explicit operator mapping `LAYOUT_FEEDER_01..08 -> LINEA 1..8` yields:
- 8 resolved feeder labels
- 0 unresolved feeder labels
- unchanged 55 CU→feeder memberships

No Ground Truth is used in either step.
