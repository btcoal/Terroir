# UF-005 backlog recalibration record

**Date:** 2026-07-25 · **Reviewed:** every open ticket UF-010 → UF-064

## Scope and ordering changes already applied

- UF-020 pulled into the M1 working set (dependency of UF-013); recorded in
  the backlog ordering note.
- UF-016 specified in M1, executed in M2 behind UF-021's real cardinality.
- UF-013 builds from the published-vintage superset, verified later by
  UF-021's coverage check.
- UF-010A added: measured volume/compute figures replace the provisional
  `assumptions.md` before M1 sizing is trusted.

## Split decisions

- **UF-011 (L):** reviewed for split; kept whole. The schema set is one
  reviewable surface; splitting by layer would force cross-PR foreign keys.
- **UF-023 (L):** kept whole but its checkpoint/resume criteria are the
  riskiest part; if the UF-010A measurements show closure sizes at the high
  end of the estimate range, split object-level resume into a child ticket
  before starting.
- **UF-033 (L):** flagged as the most likely oversized ticket in M3
  (interval inference + conflict resolution + golden fixtures). Decision
  deferred to M2 exit with a default to split inference from fixtures.
- **UF-070:** already mandates per-issuer-class child splits; unchanged.

## Size recalibration (completed with UF-010A, 2026-07-25)

Reviewed against measured closure size, parse time, and RSS
(`spike-uf010a-report.md`):

- **UF-013**: L → M candidate. Seven vintages of taxonomy resources fit in
  ~170 cached files; the superset enumeration is smaller than sized.
- **UF-023**: keeps L. The binding constraints are the ~2 TB disk purchase
  (now on its checklist) and the ~3.4M-request budget, not parse compute.
  The object-level-resume child-split trigger (high-end closure sizes) did
  NOT fire: median closure is 2 MB.
- **UF-025**: keeps L for supervision/atomicity, but the load-test scope
  shrinks — RSS recycling thresholds are generous at 210 MB median.
- **UF-021**: keeps L; gains a requirement to expose per-accession XBRL
  presence (the 2010–2011 cliff makes this a first-class inventory column).
- All other M1/M2 tickets: no size change indicated.
