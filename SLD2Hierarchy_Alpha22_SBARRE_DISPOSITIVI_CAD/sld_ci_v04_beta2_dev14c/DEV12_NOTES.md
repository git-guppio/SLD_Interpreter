# beta2-dev12 — Breakpoint classification before graph bridging

Dev12 changes the Human-in-the-Loop contract for feeder-path breakpoints.
A geometric discontinuity suggested by the tracer is no longer treated as a
candidate bridge by default. The operator first classifies the exact breakpoint:

- `CONDUCTIVE_CONTINUITY`: A and B are the same conductor path; an exact
  instance-only bridge may be added.
- `INTERPOSED_DEVICE`: a real electrical device lies between A and B; no bridge
  is added. Device type can optionally be recorded (e.g. sectionalizing cabinet,
  switch/disconnector, circuit breaker, transformer, other).
- `UNRESOLVED`: the operator cannot determine the condition safely; no bridge is
  added.

Safety / provenance rules:

- breakpoint reviews are exact-instance `OPERATOR_PROVIDED` evidence and are not
  promoted to learned geometric rules;
- an interposed device is never auto-bridged and its operational connectivity
  state is stored as `UNKNOWN`;
- wider candidate gaps that would bypass a reviewed interposed device are
  suppressed from subsequent suggestions;
- confirmed conductive continuity can repair only the exact reviewed gap;
- existing plant-scoped root/XFR calibration remains available;
- duplicate current-feedback + learned-pattern copies are deduplicated before
  application, so calibration counts do not double-report the same pattern.

GUI changes:

- Italian breakpoint-review workflow;
- button `Esamina il prossimo punto di interruzione`;
- A/B are shown automatically; no extra clicks are required;
- three explicit radio choices: continuity / interposed device / unresolved;
- optional canonical device-type selector;
- the old exact bridge path is retained only for backward compatibility and is
  not exposed as the normal workflow.

Regression suite: 41 tests.
