# beta2_dev5 checkpoint

## Why dev5

PV8 exposed a document-structure issue rather than a missing-device issue. The overview sheet does not fully enumerate transformer representations for every CU, while each subsequent Subcampo detail sheet contains the local equipment distribution. The pipeline therefore must resolve document/detail-page context before escalating to the operator.

## Changes

- `A SUBCAMPO n`, `DE SUBCAMPO n`, `TO SUBCAMPO n`, `FROM SUBCAMPO n` are treated as `REFERENCE`, not CU instances for page ownership.
- Added voltage-ratio evidence extraction, including compact notations such as `0,36/33KV` and `33KV/360V/360V`.
- Added `detail_page_resolution.py`.
- A page can acquire a CU scope from a unique local CU instance; a conservative dominant-child-tag fallback is available.
- A local apparent-power rating + nearby voltage-ratio cluster may infer a transformer only when:
  1. the page CU context is resolved;
  2. no explicit target-transformer INSTANCE/TAG already takes precedence;
  3. the voltage levels resolve the transformer role.
- Inferred transformer instances are marked `INFERRED`, not `DETECTED`.
- Hierarchical membership uses `DETAIL_PAGE_CU_CONTEXT` and counts remain hierarchy-derived.
- Overview/detail repetition is not interpreted as additional assets merely because a representation appears on another sheet.

## PV8 source-level semantic validation

Without Ground Truth, native text across the 56-sheet PV8 source shows:
- sheet 1: overview with 55 CABINA labels;
- sheets 2-56: 55 detail sheets, each with one local Subcampo context;
- each detail sheet contains two local `1600 kVA` ratings and two nearby `0,36/33KV` voltage-ratio strings.

The dev5 semantic resolver produces 110 `MV_LV_TRANSFORMER` instances, exactly two for each of the 55 resolved CU page contexts, with zero unresolved semantic clusters. This is a source-evidence result, not benchmark-guided inference.

## Tests

10 unit tests pass, covering prior dev3/dev4 behavior plus:
- cross-sheet Subcampo reference handling;
- voltage-ratio parsing;
- two transformer semantic clusters on a CU detail page;
- transformer-to-CU hierarchical attachment.
