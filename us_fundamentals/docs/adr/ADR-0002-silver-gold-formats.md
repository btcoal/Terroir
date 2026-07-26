# ADR-0002 — Silver and Gold live in Parquet long tables

**Status:** Accepted · 2026-07-25

## Decision

Silver (raw facts, contexts, relationships) and Gold (canonical observations,
effective intervals) are Parquet datasets in long form, partitioned by year
(filing year for Silver, availability year for Gold), written only by build
jobs and read through DuckDB. PostgreSQL holds metadata and mutable workflow
state, never analytical fact rows.

## Rationale

- The workloads are columnar scans: PIT snapshots, cross-sections by metric,
  company histories. Parquet + DuckDB serves these without a database server
  in the read path.
- Long form (one fact/observation per row) is the only shape that preserves
  full provenance per value and survives dictionary growth without schema
  migration; wide marts are derived products, explicitly deferred.
- Parquet files are immutable, which matches the dataset-versioning model
  (ADR-0007): a new version is new files, never edits.

## Consequences

- Physical layout (sort order, row-group sizing, partition grain) is *not*
  decided here; UF-016 decides it from measured workloads on real
  cardinality and records its own ADR.
- Equivalence between builds is logical, not byte-level (ADR-0008), because
  Parquet encoding is not canonical across writer versions or settings.
