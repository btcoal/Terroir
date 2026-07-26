# ADR-0006 — Arelle runs in a supervised local process pool

**Status:** Accepted · 2026-07-25

## Decision

XBRL parsing uses Arelle in worker *processes* on the same host, supervised
by the pipeline: workers preload the offline taxonomy cache, accept
filing-level jobs, are recycled after a configurable filing count or RSS
threshold, and are killed on a per-filing timeout. Arelle is never imported
into the orchestrating process, and there is no network parsing service in
Release 1.

## Rationale

- Arelle's memory behavior over many filings is the dominant operational
  risk; process isolation turns leaks and crashes into a recycled worker and
  a classified filing failure instead of a dead pipeline.
- Warm workers amortize taxonomy load, which UF-010A confirmed dominates
  cold cost: ~6 s first parse per vintage with a cold cache versus 0.6 s
  median with the taxonomy cache warm (`spike-uf010a-report.md`). Measured
  RSS (210 MB median, 412 MB max) supports 8–12 workers on the current
  14 GB host.
- A local pool has no serialization, auth, or deployment surface; a
  microservice adds all three for zero benefit on one host.

## The measured condition that justifies a network service

Promote to a network parsing service only when the UF-025 load test (or
production telemetry) shows **sustained parse throughput below the backfill
requirement on the largest single available host** — concretely: projected
backfill wall-clock exceeding its SLO (`assumptions.md`) with CPU or RSS on
one host as the binding constraint. Until that measurement exists,
distribution is explicitly deferred (see backlog follow-ons).

## Consequences

- Worker protocol (staging directory + structured result JSON) is defined at
  UF-025; publication must be atomic so a crash cannot expose partial Silver.
- Per-vintage worker partitioning keeps taxonomy caches hot and bounds the
  blast radius of a bad vintage.
