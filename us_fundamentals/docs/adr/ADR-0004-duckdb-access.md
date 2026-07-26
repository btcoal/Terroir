# ADR-0004 — DuckDB is the analytical access layer

**Status:** Accepted · 2026-07-25

## Decision

All analytical reads — PIT views, research queries, QC scans, benchmarks —
go through DuckDB over the Parquet datasets. The PIT resolution API (UF-049)
is implemented as DuckDB views/macros over the effective-interval tables.
No long-lived DuckDB database file is a source of truth; `.duckdb` files are
disposable caches.

## Rationale

- DuckDB reads partitioned Parquet with predicate pushdown, giving the
  UF-016 benchmark real levers (partition pruning, row-group skipping)
  without a serving cluster.
- Embedding in-process keeps research reproducible: a manifest plus Parquet
  paths fully determines query results; there is no server whose state can
  drift.

## Consequences

- Concurrency is single-process per query workload; that is acceptable for
  Release 1's research access pattern and revisited only with evidence.
- DuckDB version is pinned in the lockfile and recorded in build manifests,
  since query semantics participate in reproducibility.
