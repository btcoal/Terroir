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

## Size recalibration

Deferred to UF-010A results by design — recalibrating from the provisional
estimates would launder guesses into commitments. The `assumptions.md`
revision log is the trigger: when UF-010A lands, sizes for UF-011–UF-016 and
UF-020–UF-027 are re-reviewed against measured closure size, parse time, and
RSS (owner: whoever lands UF-010A, in the same change).
