# beta2-dev10 — feeder membership vs electrical-path verification

Dev10 extends dev9 without changing the already validated document-local
`template + schedule` model.  Its purpose is to separate **membership evidence**
from **electrical topology verification**.

## New evidence path

### 1. Explicit MV circuit schedules

Pages containing positioned rows under a title such as:

`MV-03 CIRCUIT SCHEDULE`

are parsed as `MV_CIRCUIT_SCHEDULE`.  A row is accepted only if the positioned
columns `BLOCK #`, wiring pattern, combiner count, module manufacturer and detail
sheet align on one baseline.  The resulting relation:

`BLOCK/CU -> MV feeder`

has source status `DETECTED` and basis `EXPLICIT_MV_CIRCUIT_SCHEDULE`.

The schedule resolves *membership only*.  It does **not** claim that the feeder
has been graph-traced.

### 2. Feeder verification layer

`feeder_verification.py` maintains separate channels:

- explicit source membership;
- SLD XFR identity cross-check;
- graph-verified membership where a real shared electrical graph component is
  available;
- hard graph conflicts;
- feeder trace status;
- grouped operator request when a feeder cannot yet be electrically traversed.

The operator request is deliberately feeder/path oriented.  It asks for a
missing or ambiguous path segment / breakpoint, not for manual re-entry of every
CU-to-feeder assignment.

### 3. Trace origin policy

The preferred logical origin is:

1. HV/MV transformer secondary, when represented;
2. MV busbar, when represented;
3. substation breaker/project-substation feeder origin;
4. feeder label only when upstream equipment is outside drawing scope.

The target direction is then downstream through CU -> MV/LV transformer ->
inverter -> LV/DC collection equipment.  A cross-sheet template may establish
hierarchy, but an end-to-end graph trace is only marked complete when actual
connectivity supports it.

### 4. No schedule-order shortcut

Circuit-schedule row order is **never** treated as electrical order along the
feeder.  Until graph traversal resolves the sequence, `electrical_order_status`
remains `UNRESOLVED`.

## Roadrunner source preflight

Using original Roadrunner pages 3-25 as the auxiliary layout source, native text
preflight detects:

- 164 explicit MV circuit-schedule rows;
- 164 unique Block/CU identities;
- 16 feeders `MV-01 ... MV-16`;
- no block listed in two different feeder schedules;
- no spurious `MV-105` line identity from cable-insulation specifications.

These are source-derived checks, not Ground Truth inference.

## Regression policy

When no `MV_CIRCUIT_SCHEDULE` exists, dev10 preserves previous layout membership
behavior.  Dev8-style structural feeder recovery and PLANT-scoped operator label
learning remain available.

Dev10 adds four tests to the 26 inherited regressions.  Current unit suite:

`Ran 30 tests ... OK`

The full 10-PV corpus regression remains a required validation step before dev10
is promoted to a stable checkpoint.
