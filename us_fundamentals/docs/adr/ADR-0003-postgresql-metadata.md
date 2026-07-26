# ADR-0003 — PostgreSQL is the metadata and workflow-state store

**Status:** Accepted · 2026-07-25

## Decision

One PostgreSQL database holds: accession inventory and ingestion state,
object manifests, entity/security/listing history, mapping rules and review
state, QC results, comparability events, run records, and dataset-release
metadata. Migrations are plain SQL with paired forward/rollback files
(UF-011), applied by a small stdlib runner — no ORM, no migration framework.

## Rationale

- This state is relational, mutable, and constraint-hungry: uniqueness on
  accession, temporal non-overlap on listings, foreign keys from QC results
  to rules. PostgreSQL enforces these; Parquet cannot.
- Plain SQL migrations keep the schema reviewable in diffs and testable by
  round-trip (forward, rollback, forward) against empty and populated
  databases.
- No ORM: the pipeline's queries are few and explicit; an ORM would blur the
  boundary between workflow state (SQL) and analytical data (Parquet).

## Consequences

- Local development and CI use a per-run scratch database; peer auth locally,
  password auth via environment in other profiles (UF-010 config).
- Analytical queries never join live against PostgreSQL; anything Research
  needs is exported into versioned Parquet.
