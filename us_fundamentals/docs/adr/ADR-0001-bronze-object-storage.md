# ADR-0001 — Bronze object storage: content-addressed local filesystem, S3-shaped

**Status:** Accepted · 2026-07-25

## Decision

Bronze parser inputs are stored as content-addressed objects
(`sha256/<first2>/<hash>`) on a local filesystem, behind a small store
interface whose operations (`put_bytes`, `get`, `exists`, `verify`) are
deliberately restricted to what an S3-compatible object store also offers.
No component may rely on rename atomicity, directory listing order, or
mutation of a stored object.

## Rationale

- Content addressing makes idempotent reacquisition and hash-mismatch
  detection (UF-012) structural rather than procedural: identical bytes land
  on the same key; different bytes for the same logical object are a terminal
  integrity event, never an overwrite.
- The single-node backfill fits on local NVMe (see `assumptions.md`); paying
  for object-store latency and egress during the first backfill buys nothing.
- Keeping the interface S3-shaped means promotion to MinIO/S3 is a store
  swap, not a redesign.

## Consequences

- Accession manifests (UF-012) are the only mapping from filing to objects;
  losing manifests loses addressability, so manifests live in PostgreSQL and
  in a manifest file beside the objects.
- Garbage collection is manifest-driven and out of scope until a release
  exists.

## Revisit when

Backfill storage exceeds a single node (~2 TB) or multi-host workers need
shared Bronze access.
