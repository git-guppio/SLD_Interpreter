# DEV14C NOTES

Patch focused on operator clarity and non-electrical graphics.

- Adds breakpoint classification `NON_ELECTRICAL_GRAPHIC` for dashed area boundaries,
  enclosure borders, annotations and other visible elements that are not part of the
  power circuit.
- This classification never creates a conductive bridge and never creates an
  electrical device. The exact reviewed graph nodes are excluded from feeder tracing
  for that feeder/page.
- Old `UNRESOLVED` breakpoint decisions created before this option existed are offered
  once again so the operator can reclassify them explicitly; new schema-v2 unresolved
  decisions are not looped.
- The simplified Italian GUI now exposes four clear choices for breakpoint review.
- PowerShell progress rendering clears stale text when a shorter phase label replaces a
  longer one.
- No global rule such as "all dashed lines are non-electrical" is learned from one
  operator decision. The exclusion remains instance / feeder / page scoped.
