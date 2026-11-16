# beta2-dev10 — document-local template/schedule generalization

Dev9 is the first checkpoint aimed at SLD families where a CU is not described by
one detail sheet per container.  It keeps dev8 conservative rules and adds a
cross-source resolver for `template + instance schedule` document structures.

## New behavior

1. **Functional sheet-title priority**
   - `SINGLE LINE DIAGRAM` outranks incidental schedule tables on the same page.
   - This prevents an SLD with embedded schedules from being classified as a
     generic schedule page.

2. **Layout page-role refinement**
   - `PLANT_LAYOUT_OVERVIEW`
   - `CONTAINER_SCHEDULE`
   - `MV_NETWORK_LAYOUT`
   Page role is semantic and does not depend on page number.

3. **Positioned BLOCK SCHEDULE parser**
   Rows are accepted only when the block id, wiring-pattern token, combiner-box
   count, module manufacturer and detail-sheet reference align on the same table
   row.  Text extraction order alone is never used to manufacture rows.

4. **Document-local CU model**
   `POWER BLOCK`, `SKID` and `XFR` are **not** global aliases.  A local CU model is
   inferred only when the current plant provides converging independent evidence:
   explicit block identities + explicit XFR identities + exact identifier-set
   alignment + block/skid document context.

5. **Template expansion with provenance**
   When a source explicitly states one typical inverter for the skid population,
   one inverter may be instantiated per resolved CU as `INFERRED`.  Combiner-box
   cardinality comes from each positioned schedule row and creates inferred
   STRING_BOX children.  XFR instances can be classified as MV/LV transformers
   only when the same document contains step-up transformer / from-inverter
   semantics on electrical SLD sheets.

6. **Standalone MV identifiers**
   Explicit `MV-01`, `MV_01`, etc. are recognized, including multiple identifiers
   packed into a single PDF text span.  The line name is source-detected; no
   operator mapping is needed when the label is readable.

## Roadrunner/PV4 preflight (source-derived, no benchmark)

Using the separated Roadrunner files prepared for CASE_004, the text/semantic
preflight resolves:

- 164 positioned block-schedule rows;
- 164 unique XFR instance identifiers;
- exact block/XFR identifier-set alignment;
- 2,389 combiner boxes from the per-block schedule cardinalities;
- source template evidence `TYPICAL FOR 164 SKIDS`;
- 16 readable MV line identifiers (`MV-01` ... `MV-16`).

The resulting target hierarchy preflight is therefore 164 CU, 164 MV/LV
transformers, 164 central inverters and 2,389 string/combiner boxes, all without
Ground Truth.  CU, inverter and schedule-expanded string-box instances are
`INFERRED`; XFR identity is source-detected but its MV/LV classification remains
an inferred semantic resolution.

CU-to-MV membership is deliberately not forced by these counts.  It remains a
separate topology problem and can remain unresolved if graph evidence is not
strong enough.

## Regression tests

`26` tests pass, including all dev3-dev8 regressions plus four dev9 tests for:
functional-title precedence, positioned schedule parsing, multiple standalone MV
identifiers in one text span, and document-local template expansion.
