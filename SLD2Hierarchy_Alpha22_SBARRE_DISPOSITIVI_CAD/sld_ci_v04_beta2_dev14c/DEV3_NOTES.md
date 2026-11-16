# beta2-dev3 implementation notes

Changes in this checkpoint:

- Added `operator_visual.py`, a local Tkinter/PyMuPDF visual resolver.
- Open `VISUAL_SELECT` requests can be reviewed directly against the original PDF.
- Relevant unresolved candidate groups are highlighted as navigation aids only.
- Operator can zoom, pan, focus candidates, and draw a rectangle around the device.
- PDF-coordinate conversion supports rotated pages using PyMuPDF rotation matrices.
- Feedback outcomes are explicitly one of:
  - `SELECT_DEVICE`
  - `NOT_REPRESENTED_IN_SLD`
  - `UNABLE_TO_IDENTIFY`
- `SELECT_DEVICE` requires a target device class and stores `OPERATOR_PROVIDED` provenance.
- Existing feedback for the same request is replaced when the operator deliberately saves a new terminal outcome.
- `resolution_engine.py` now emits `visual_hints` with group/page/bbox/morph-family/terminal-count metadata.
- No source detector or automatic acceptance threshold was relaxed.
- CLI/result version updated to `0.4.0-beta2-dev3`.

Safety / inference policy:

- Operator rectangles are evidence for the current run, not global shape-to-class rules.
- Direct SLD evidence still has precedence over learned knowledge.
- A selection with no candidate overlap is preserved as `DETECTION_FAILURE`.
- Ground truth remains outside inference.

## PV5 identity-collision investigation

A real dev3 run on `PV5.pdf` confirmed the historic 189-vs-188 String Box discrepancy:

- raw explicit String Box INSTANCE/TAG anchors: 189
- unique resolved String Box identities by source tag: 188
- collision: `CLT-CST-01-I01-12-02` appears on pages 2 and 14
- page 2 direct CU context = CU 1, consistent with the parsed tag
- page 14 direct CU context = CU 7, while the repeated tag still parses as CU 1

The resolver now reports this as `POSSIBLE_MISTAG_OR_DUPLICATE_INSTANCE` with
`DIAGNOSTIC_ONLY_NO_AUTOMATIC_TAG_CORRECTION`. It does not silently rewrite the
source tag and does not use benchmark ground truth to decide whether the correct
asset count is 188 or 189.

New target-entity diagnostics:
- `raw_source_instance_counts`
- `source_instance_collisions`
- `identity_resolution_complete`

Synthetic dev3 tests added for visual-hint generation, rotated coordinate
round-trip and duplicate-tag/page-context conflict detection. All pass.
