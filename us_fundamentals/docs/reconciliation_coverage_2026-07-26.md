# UF-022 bulk reconciliation ingest record — 2026-07-26

Sources under `data/bulk/` (cataloged append-only by content hash in
`data/bulk/source_catalog.json`): `companyfacts.zip` (1.3 GB) and 65 FSDS
quarterly archives 2010Q1–2026Q1 (5.2 GB; 2026Q2 not yet published
upstream, recorded as missing).

## Ingested

- FSDS `sub` + `num` tables → 4.5 GB vintage-keyed Parquet, 65 quarters,
  ~2.5–3.8M num rows per recent quarter, in 138 s. Notes tables not
  ingested by design.
- Company Facts per-accession presence index: 20,096 CIK files scanned,
  **448,274 accessions**, vintage `companyfacts:4ad69aeb84df`.

## Coverage vs. the UF-021 accession inventory (1,014,676 rows)

| Check | Result |
| --- | --- |
| Company Facts accessions matched to inventory | 405,848 |
| XBRL-flagged inventory rows absent from Company Facts | **474** (≈0.1%) — reconciliation review targets for UF-052 |
| FSDS distinct accessions | 425,062 |
| FSDS matched to inventory | 393,770 (unmatched are non-10-K/Q forms FSDS also covers) |

Rebuild: `uv run python -m us_fundamentals.bulk_reconciliation ingest-fsds
data/bulk/fsds/*.zip --out-dir data/reconciliation/fsds --catalog
data/bulk/source_catalog.json`, then `index-companyfacts`, then `coverage`.
