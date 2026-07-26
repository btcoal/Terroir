# ADR-0009 — Gold physical layout: year partitions, entity-major sort

**Status:** Accepted · 2026-07-26 · **Benchmark:** `scripts/benchmark_uf016.py`
(report regenerates to `data/benchmarks/uf016/report.json`)

## Decision

Gold long tables (canonical observations and their effective-interval
materialization) are Parquet, partitioned by **`available_year`** only,
sorted **`entity_id, metric_id, available_at`**, with DuckDB's default
122,880-row row groups. Metric-group subpartitioning is rejected.

## Evidence

Synthetic 12.4M-row effective-interval table generated from the *real*
UF-021 inventory cardinality (18,675 entities, 497,117 denominator
accessions, 9.18% amendment rate, per-year filing skew 2010→2026; inventory
logical hash `77c62401…`, see `docs/inventory_snapshot_2026-07-25.md`).
Three candidates, three workloads, best of three runs:

| Layout | Storage | PIT `as_of` cross-section | Metric-year slice | Company history | Incremental year append |
| --- | --- | --- | --- | --- | --- |
| year + PIT sort (`metric, entity, available_at, period_end`) | 348 MB | 0.47 s | 9 ms | 28 ms | 0.51 s / 12.4 MB |
| **year + entity-major sort (`entity, metric, available_at`)** | **122 MB** | 0.48 s | 8 ms | **5 ms** | **0.25 s / 6.3 MB** |
| year + metric-group subpartition, PIT sort | 350 MB | 0.50 s | 11 ms | 37 ms | 0.40 s / 12.4 MB |

- Entity-major sorting compresses 2.9× better: entity-correlated columns
  (entity, accession, period) become long runs, and that dominates total
  bytes scanned for every query.
- The PIT cross-section is insensitive to sort order (metric predicate
  pushdown works in both), so the sort choice is decided by the workloads
  that *do* differ: company history (5 ms vs 28 ms) and write cost.
- Metric-group subpartitioning adds file count and write cost, wins
  nothing: metric predicates already prune via row-group statistics.
- All results are ~20× inside the UF-016 `< 10 s` PIT target at full
  Release 1 scale on one host.

## Consequences

- UF-049's effective-interval tables adopt this layout; the PIT view reads
  `available_year <= year(as_of)` partitions with interval predicates.
- Row-group sizing stays at the DuckDB default until a measured regression
  says otherwise; the benchmark is re-runnable in one command against any
  future inventory snapshot.
- Silver keeps filing-year partitioning (larger, append-only, scanned by
  parse-oriented jobs); this ADR governs Gold and Research outputs.
