# Volume, compute, SLO, and cost assumptions

**Status:** Provisional — every figure here is an estimate recorded before
any measurement. UF-010A replaces this section with measured values and marks
the revision explicitly; sizes in the backlog are recalibrated from the
measured figures, not these.

## Data volume (estimated)

| Quantity | Estimate | Basis |
| --- | --- | --- |
| Eligible accessions, 2010→present | ~450,000 | ~5,500 active filers × 4 filings/yr × 16.5 yrs, plus amendments, minus exclusions — unmeasured until UF-021 |
| Parser-input closure per accession | ~3–8 MB stored (median) | iXBRL primary doc dominates; large filers 20–50 MB |
| Bronze total | ~1.5–3.5 TB | closure × accessions; the widest error bars in this table |
| Silver Parquet | ~150–400 GB | facts + contexts + relationships, long form, compressed |
| Gold + Research Parquet | ~20–60 GB | canonical observations + intervals + derived |
| PostgreSQL metadata | ~50–100 GB | inventory, manifests, QC results dominate |

## Compute envelope (estimated)

| Quantity | Estimate | Basis |
| --- | --- | --- |
| Arelle parse, warm worker | ~2–10 s/filing (median) | folklore; UF-010A measures |
| Backfill parse wall-clock | ~10–40 days × 1 host (16 cores) | 450k filings ÷ (cores × filings/s); acquisition is rate-capped separately |
| Acquisition wall-clock | ~8–20 days | ~3.6M objects at <10 req/s aggregate, bulk archives first |
| Peak RSS per worker | ~1–4 GB | drives worker count on a 14 GB host — likely 4–6 workers, not 16 |

## Service-level objectives

| SLO | Target |
| --- | --- |
| Historical backfill (M6) | complete in < 60 days wall-clock on one host |
| Nightly incremental (UF-062) | new filing → published candidate rows < 24 h |
| Clean rebuild from pinned manifest | < 14 days, no manual steps |
| PIT query (UF-016 target) | representative `as_of` snapshot < 10 s on one host |

## Cost assumptions

Single existing workstation (16 cores / 14 GB / NVMe): no incremental
hardware cost; ~2–4 TB disk headroom is the binding constraint and may
require one ~$200–400 drive. SEC data is free; no licensed data in Release 1.
LLM review-packet costs are deferred to UF-042/043 sizing. If Bronze exceeds
local disk, object storage at ~$0.005–0.023/GB·mo (~$10–80/mo for 2–3.5 TB)
is the fallback recorded in ADR-0001.

## Revision log

| Date | Change |
| --- | --- |
| 2026-07-25 | Initial provisional estimates (pre-measurement) |
