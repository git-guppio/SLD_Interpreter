DEV11E

# sld_ci_v04_beta2_dev11c

Patch di avvio GUI rispetto a dev11b. La logica di interpretazione è invariata.

# Electrical SLD Interpreter — beta2-dev10

**Dev10 focus:** explicit MV circuit-schedule membership plus a separate feeder electrical-path verification layer. Membership can be source-resolved without falsely claiming graph verification. Operator assistance is requested at feeder/path breakpoints, not as bulk manual CU assignment.

See `DEV10_NOTES.md` for the dev10 evidence and regression policy.


Checkpoint conservativo per SLD fotovoltaici eterogenei. Dev9 estende dev8 con
un modello **document-local template + schedule**, senza introdurre alias globali
specifici di Roadrunner.

## Input consigliato

```text
CASE_00x_PVx/
  input/
    PVx_SLD.pdf
    PVx_LAYOUT.pdf   # opzionale
  output/
```

Lo SLD resta la sorgente primaria della gerarchia equipment. Il layout è una
sorgente ausiliaria per identità CU, schedule e topologia MT. Le due sorgenti
vengono riconciliate senza duplicare asset.

## Avvio Windows / PowerShell

```powershell
python -m unittest discover -s .\sld_ci_v04_beta2_dev10\tests -v

python -m sld_ci_v04_beta2_dev10.cli `
  --sld "..\data\CASE_004_PV4\input\PV4_SLD.pdf" `
  --layout "..\data\CASE_004_PV4\input\PV4_LAYOUT.pdf" `
  --out "..\data\CASE_004_PV4\output\PV4_dev9_blind.json" `
  --knowledge-store ".\sld_ci_v04_beta2_dev10\knowledge\knowledge_store.json"
```

Tesseract serve solo quando l'OCR viene effettivamente attivato. Non vengono
usate API esterne e il Ground Truth non entra nell'inferenza.

## Novità dev9

- `SINGLE LINE DIAGRAM` ha priorità funzionale sulle tabelle embedded.
- Ruoli layout distinti: overview, container schedule, MV network layout.
- Parser posizionale delle righe `BLOCK SCHEDULE`.
- Resolver document-local per correlare Power Block / Skid / XFR solo quando
  convergono identità e semantica della sorgente.
- Espansione `INFERRED` del template per inverter e cardinalità combiner-box.
- Riconoscimento esplicito `MV-01`, `MV_01`, ecc., anche quando più ID sono nello
  stesso text span.
- Nessun alias globale `POWER BLOCK = CU` o `XFR = CU`.

Vedi `DEV9_NOTES.md` per criteri, provenienza e preflight Roadrunner/PV4.

## beta2-dev2 — Minimum Target Hierarchy foundation

Added downstream-only infrastructure; existing detector/acceptance rules are not
made more permissive.

- `candidate_feature_extraction.py`: stable Minimum Feature Set for candidate
  groups; morphology/repetition is evidence only and never an equipment class.
- `resolution_models.py` + `resolution_engine.py`: structured unresolved requests
  for future operator interaction. Generic paired-circle geometry remains
  unresolved and can trigger a `VISUAL_SELECT` request.
- `operator_interaction.py`: UI-independent feedback contract preserving
  `OPERATOR_PROVIDED` provenance.
- `knowledge_store.py` + `knowledge/knowledge_store.json`: local, auditable store
  for reusable operator-taught patterns. Empty by default; no ground truth is
  imported.
- `decision_pipeline.interpret`: exposes `candidate_feature_profiles` and
  `resolution_requests` without changing the current automatic acceptance gate.

Target hierarchy for the next steps:
`PLANT -> CONVERSION_UNIT -> {IOCB, MV_LV_TRANSFORMER, INVERTER}` and
`INVERTER -> {LV_LV_TRANSFORMER, STRING_BOX}`. Counts must be derived from
resolved membership, not from global totals.


## beta2-dev2 — Minimum target hierarchy and Human-in-the-Loop

Added:
- `container_resolution.py`: CU/container identity resolved independently from physical symbols.
- `target_hierarchy.py`: minimum hierarchy and counts derived only from resolved membership.
- `operator_feedback_resolution.py`: visual/operator classification of unresolved groups; distinguishes classification failure from detection failure.
- `operator_learning.py`: conservative lexical pattern induction from operator-provided CU examples.
- persistent `knowledge_store` schema v2; direct SLD evidence always has precedence.
- CLI options `--knowledge-store` and `--operator-feedback`.

Minimum target hierarchy:
`PLANT -> CONVERSION_UNIT -> {IOCB, MV_LV_TRANSFORMER, CENTRAL_INVERTER -> {LV_LV_TRANSFORMER, STRING_BOX}}`.

Operator data is valid for the current run but remains explicitly `OPERATOR_PROVIDED`.
Visual selections do not automatically teach a universal shape-to-class mapping.


## beta2-dev5 — Visual operator resolver

This checkpoint adds a local Tkinter visual resolver for open `VISUAL_SELECT`
requests. It is downstream of automatic inference: it does not alter the source
detectors and it never converts a visual shape into a universal equipment rule.

Typical two-pass workflow:

```powershell
python -m sld_ci_v04_beta2_dev10.cli `
  --pdf "C:\path\PV10.pdf" `
  --out "output\PV10_dev5.json" `
  --knowledge-store "knowledge\knowledge_store.json"

python -m sld_ci_v04_beta2_dev10.operator_visual `
  --pdf "C:\path\PV10.pdf" `
  --analysis "output\PV10_dev5.json" `
  --feedback "output\PV10_operator_feedback.json"

python -m sld_ci_v04_beta2_dev10.cli `
  --pdf "C:\path\PV10.pdf" `
  --out "output\PV10_dev5_resolved.json" `
  --knowledge-store "knowledge\knowledge_store.json" `
  --operator-feedback "output\PV10_operator_feedback.json"
```

The visual tool shows the relevant SLD page, highlights unresolved candidates,
supports zoom/pan, lets the operator draw a rectangular PDF-coordinate selection,
and records one of: `SELECT_DEVICE`, `NOT_REPRESENTED_IN_SLD`, or
`UNABLE_TO_IDENTIFY`. The selection remains explicitly `OPERATOR_PROVIDED`.
If the rectangle overlaps an existing candidate, the existing group can be
classified; otherwise the event remains a `DETECTION_FAILURE` diagnostic.

`resolution_requests` now include `visual_hints` (page, bbox, morphology family,
terminal count) to make the UI navigable without changing classification logic.


## dev4 clarification
The CLI now prints **ANALYSIS COUNTS** separately from **TARGET COUNTS**. Only TARGET COUNTS are asset counts for the minimum hierarchy. Apparent-power ratings (kVA/MVA) are semantic evidence only and can trigger a visual resolution request; they never classify a transformer by themselves.

## beta2-dev5 — detail-page semantic resolution

`dev5` adds a document-structure layer for SLDs where the overview and detail sheets expose different amounts of equipment detail.

The important rule is not PV8-specific: cross-sheet references do not establish page ownership, while a resolved local container context can scope local equipment evidence. A transformer can be inferred from a local cluster of apparent-power rating plus voltage-ratio evidence only when the container context is resolved and no stronger explicit transformer instance/tag already exists.

The inferred asset keeps `source_status=INFERRED`; direct source tags and operator-provided information retain their higher/explicit provenance.

## beta2-dev6 — primary SLD + optional layout

The case can contain `PVx_SLD.pdf` as the primary equipment source and an optional `PVx_LAYOUT.pdf` as auxiliary plant-topology evidence. Layout pages never inflate SLD equipment counts. Page role is resolved independently of ordinal page number, and CU identity is reconciled across sources.

## beta2-dev7 — structural layout feeder fallback

When explicit MV-line text in the layout is readable, dev7 keeps the dev6 rule: direct source identity is preferred. If the PDF text layer corrupts feeder labels, dev7 can recover repeated top-level feeder trunks from vector geometry and group CU representations under synthetic feeder keys. Source feeder labels remain `UNRESOLVED` until readable source text or operator confirmation is available. This preserves topology without inventing line names.

## beta2-dev8 — operator-resolved MV feeder labels

Dev8 adds a grouped Human-in-the-Loop request for structural MV feeders whose native layout labels are unreadable. `operator_layout.py` shows each synthetic feeder together with the CU instances already attached to it and records the operator's actual line labels with `OPERATOR_PROVIDED` provenance. The CU-to-feeder topology remains independently `INFERRED`.

Mappings learned from operator input are intentionally scoped to the same plant; dev8 does not generalize a left-to-right numbering convention across plants. Readable direct source labels always take precedence.

## Dev11 — operator-assisted feeder graph calibration

Dev11 adds `operator_feeder.py`. It is used only after automatic CU→MV membership is already known but graph verification is incomplete. It calibrates feeder roots, repeated XFR MV terminals, and explicit conductor breakpoints while preserving `OPERATOR_PROVIDED` provenance. Exact graph bridges are never generalized; repeated geometric patterns are plant-scoped and must never bridge transformer windings.

See `DEV11_NOTES.md` for the workflow.


## dev11b GUI revision
The feeder calibration GUI is now guided and Italian-language. Backend inference logic is unchanged from dev11. See `DEV11B_NOTES.md`.


## dev11d
Patch UI: pannello sinistro scorrevole e barra azioni fissa; backend invariato rispetto a dev11c.


Vedi DEV11E_NOTES.md per le modifiche alla GUI guidata e alla suite di regressione.


## dev12 GUI
Il pulsante di conferma è ora visibile direttamente sotto i pulsanti A/B. Dopo il clic sul punto blu usare **Conferma e salva PASSO A/B**, oppure `Invio` / `Ctrl+S`. La finestra usa dimensioni adattive per evitare controlli sotto la taskbar.

## beta2-dev12 — classificazione sicura dei breakpoint

Prima di creare un bridge tra due estremi A/B il motore richiede ora una
classificazione esplicita: continuità grafica, dispositivo elettrico interposto,
o non risolto. Solo la continuità grafica crea un bridge esatto. Un dispositivo
interposto viene registrato come evidenza `OPERATOR_PROVIDED`, con stato di
connettività operativo `UNKNOWN`, e non viene bypassato. I successivi breakpoint
che attraverserebbero lo stesso dispositivo vengono soppressi.

Vedi `DEV12_NOTES.md`.

## dev13
Reviewed interposed electrical devices are now inserted into the structural topology graph as equipment edges. They are not converted to conductive gap bridges; operating state remains separate. This allows feeder-path verification to continue through switchgear/cabinets while preserving device semantics.

## DEV14 — modalità operatore consigliata

Usare normalmente un solo comando:

```powershell
python -m sld_ci_v04_beta2_dev14c.workflow --case "..\data\CASE_004_PV4"
```

Il programma esegue l'analisi, mostra solo il riepilogo utile e apre automaticamente la GUI se è richiesto un intervento umano. I dettagli tecnici completi vengono conservati nel file `*_dev14_full.log`.


## dev14b — indicatore di avanzamento
Il workflow mostra una barra percentuale stimata, fase corrente e tempo trascorso sia nel primo run sia nel ricalcolo dopo la GUI.


## dev14c — elementi grafici non elettrici
La verifica breakpoint distingue ora esplicitamente un bordo/area/annotazione non elettrica da un conduttore, un dispositivo o un caso realmente incerto. Le decisioni `NON_ELECTRICAL_GRAPHIC` non vengono collegate né modellate come equipment e sono escluse dal trace del feeder per quella specifica istanza. Vedi `DEV14C_NOTES.md`.
