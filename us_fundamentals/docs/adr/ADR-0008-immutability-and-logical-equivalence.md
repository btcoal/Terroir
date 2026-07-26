# ADR-0008 — Immutable parser-input closure; logical, not byte-level, equivalence

**Status:** Accepted · 2026-07-25

## Decision

Two mandates, jointly:

1. **Immutable parser-input closure.** Every accession's parser input —
   filing index, primary/Inline XBRL document, instance, extension schema,
   consumed linkbases, labels, references, header, and every external
   document the parser consumed — is stored content-addressed before parsing
   and never modified. Parsing reads only from the closure; a re-parse years
   later sees exactly the original bytes (UF-012, enforced by the UF-013
   fail-closed offline resolver).

2. **Logical dataset equivalence.** Two builds are equivalent when their
   *logical hashes* match: hashes over normalized rows (canonical row order
   by primary key, canonical numeric and timestamp representation, explicit
   null encoding), not over Parquet bytes. Byte-identity across writer
   versions, row-group sizes, or compression settings is explicitly a non-goal
   (UF-014).

## Rationale

- Reproducibility claims fail in practice either because an input silently
  changed (fixed by 1) or because the comparison is too strict to survive
  harmless physical variation (fixed by 2). The pair is the narrowest
  contract that makes "same pinned inputs, same rules ⇒ same dataset"
  provable and durable.
- Hash mismatch on reacquisition is evidence about *the source*, so it must
  be recorded as a terminal integrity event, never resolved by overwrite.

## Consequences

- The logical-hash normalization spec (UF-014) is itself versioned; changing
  it invalidates cross-version hash comparison and requires a dataset
  version bump.
- Full-vs-incremental equivalence (UF-024, UF-062) is defined in terms of
  these logical hashes with one row-level diff command.
