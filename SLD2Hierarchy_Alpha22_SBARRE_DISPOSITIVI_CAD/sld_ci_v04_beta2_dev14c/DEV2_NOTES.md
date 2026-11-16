# beta2-dev2 implementation notes

Implemented in this checkpoint:

- Conversion Unit resolution as container entities, independent from physical-symbol detection.
- Minimum target entity resolution from explicit INSTANCE/TAG text anchors even where reliable local geometry is unavailable.
- Minimum hierarchy:
  - PLANT -> CONVERSION_UNIT
  - CONVERSION_UNIT -> IOCB / MV_LV_TRANSFORMER / CENTRAL_INVERTER
  - CENTRAL_INVERTER -> LV_LV_TRANSFORMER / STRING_BOX
- Counts are derived only from resolved parent-child membership.
- Structured operator feedback with OPERATOR_PROVIDED provenance.
- Visual-selection contract: selection can resolve an existing candidate (classification failure) or record DETECTION_FAILURE when no candidate overlaps.
- Local knowledge store schema v2.
- Conservative CU identifier-pattern induction from two or more operator-provided lexical examples.
- Learned patterns never override direct SLD evidence.

Regression checks completed in the build environment:

- Jaguito source page: PASS; 2 CU resolved.
- PV6: PASS; 2 CU, 3 MV/LV transformers, 3 inverters, 35 String Boxes; all target membership resolved.
- PV7: PASS; 1 CU, 2 MV/LV transformers, 2 inverters, 25 String Boxes; all target membership resolved.
- PV5: PASS; 7 CU, 13 MV/LV transformers, 13 inverters, 188 String Boxes in current dev2 extraction. The historic v0.2 benchmark reports 189 SB and explicitly notes a known duplicate/mistag, so this discrepancy is intentionally flagged for investigation rather than silently corrected.
- Full PV8 dev2 run was started in the build environment but exceeded the available execution window; no result is claimed.

Synthetic tests:
- direct CU resolution
- hierarchy membership from semantic instance hints
- operator lexical pattern induction
- operator visual classification of an existing candidate
- detection-failure classification for a selection with no existing candidate overlap

All five synthetic checks passed and all Python modules compile.
