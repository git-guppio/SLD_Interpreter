# DEV11b — Guided Italian feeder calibration GUI

Algorithmic backend is unchanged from dev11. This revision only improves operator interaction.

Changes:
- Italian UI text and dialogs.
- Removed the technical calibration-mode dropdown from the normal workflow.
- Two explicit guided steps: feeder electrical origin, then representative XFR MV terminal.
- Feeder-root step is now the default, preventing accidental omission.
- After saving the feeder root, the GUI automatically advances to the XFR-terminal step.
- Advanced graph-bridge actions are visually separated and marked as use-only-when-requested.
- Clear explanation that the GUI does not assign CU-to-feeder membership manually.
- Shows saved-calibration counters.
- Existing internal action codes and feedback schema are unchanged for compatibility.
