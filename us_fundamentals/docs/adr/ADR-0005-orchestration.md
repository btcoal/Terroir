# ADR-0005 — Orchestration: checkpointed CLI jobs, no workflow engine

**Status:** Accepted · 2026-07-25

## Decision

Pipeline stages are idempotent CLI commands (`python -m us_fundamentals.jobs.*`)
that record run state (run ID, stage, checkpoint, outcome) in PostgreSQL.
Sequencing is explicit in a driver script per milestone. No Airflow, Dagster,
or Prefect for Release 1.

## Rationale

- The dependency graph is static and shallow; its complexity lives *inside*
  stages (resumable acquisition, worker pools), which an engine would not
  absorb.
- Restartability comes from accession-level checkpoints in the database
  (UF-023, UF-060), so the scheduler adds availability, not correctness —
  and a single-node backfill doesn't need the availability.
- Every engine import we defer keeps the clean-checkout story (UF-010: test
  suite and minimal pipeline from documented commands) trivially true.

## Consequences

- Nightly incremental operation (UF-062) will need a scheduler; a cron entry
  invoking the same CLI jobs is the intended first step, and an engine is
  adopted only if operational evidence (missed runs, tangled retries)
  demands it.
- Run records are the audit trail; jobs that don't write them are defective.
