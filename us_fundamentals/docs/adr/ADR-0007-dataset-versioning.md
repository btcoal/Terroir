# ADR-0007 — Dataset versioning: immutable releases pinned by manifest

**Status:** Accepted · 2026-07-25

## Decision

A dataset version is an immutable, named set of outputs pinned by a release
manifest (UF-014): accession set, raw object hashes, taxonomy package
versions, parser/mapping/QC-rule/formula versions, code commit, and logical
hashes of every output table. New inputs, new rules, or corrections produce a
*new* version; nothing is edited in place. Version identity is
`release.major.minor` where major bumps on contract changes (dictionary,
policy) and minor on data-only additions or corrections.

## Rationale

- The PIT guarantee (UF-015/UF-049) is only auditable if the thing a user
  queried yesterday still exists unchanged today; mutation would make leakage
  undetectable after the fact.
- Manifest pinning is what makes "clean rebuild produces a logically
  equivalent dataset" (UF-061 gate) a testable claim rather than a hope.

## Consequences

- Storage grows per version; retention policy for superseded candidate
  versions is a UF-064 governance decision, and archived *published* PIT
  snapshots are retained per the release policy.
- Mapping-version lineage and filing-version lineage stay independent axes
  (UF-049); a dataset version pins one point on each.
