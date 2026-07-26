# Volume, compute, SLO, and cost assumptions

**Status:** Revised by UF-010A on 2026-07-25 — measured values below
supersede the original estimates, which are retained struck-through-in-
spirit in the tables' "pre-spike estimate" columns. Full methodology and
per-vintage detail: [spike-uf010a-report.md](spike-uf010a-report.md).

## Data volume

| Quantity | Pre-spike estimate | Measured / revised (UF-010A) |
| --- | --- | --- |
| Eligible accessions, 2010→present | ~450,000 | **≈480k** raw form-index rows (avg ≈7,900/qtr × 66 qtrs, declining 9.4k→6.0k); issuer exclusions and early-vintage XBRL absence reduce the parseable set — final denominator is UF-021's |
| Parser-input closure per accession | 3–8 MB median | **2.0 MB median**, p90 6.9 MB, max 33.7 MB, ~6 objects |
| Bronze total | 1.5–3.5 TB | **≈1.2–1.7 TB** |
| Silver Parquet | 150–400 GB | unchanged (unmeasured; facts/filing median 740 supports low end) |
| Gold + Research Parquet | 20–60 GB | unchanged (unmeasured) |
| PostgreSQL metadata | 50–100 GB | unchanged (unmeasured) |

## Compute envelope

| Quantity | Pre-spike estimate | Measured / revised (UF-010A) |
| --- | --- | --- |
| Arelle parse per filing | 2–10 s median | **0.6 s median / 3.1 s p90 / 6.9 s max** (fresh process, warm disk taxonomy cache); ~6 s cold-cache first parse per vintage |
| Backfill parse wall-clock | 10–40 days | **< 2 days** with 8–12 workers; parsing is no longer the driver |
| Acquisition wall-clock | 8–20 days | **≈5–10 days**: ~3.4M naive requests at 8 rps ≈ 5 days, cut further by bulk archives and early-vintage XBRL absence |
| Peak RSS per parse | 1–4 GB | **210 MB median, 412 MB max** → 8–12 workers on a 14 GB host |

The 2010–2011 XBRL cliff (9 of 11 sampled 2010Q1 filings carry no XBRL) is
the single most consequential measurement: early-vintage coverage is a
policy question (UF-001 early-vintage rules), not an acquisition defect,
and UF-021 must expose XBRL presence per accession.

## Service-level objectives

| SLO | Target |
| --- | --- |
| Historical backfill (M6) | complete in < 60 days wall-clock on one host |
| Nightly incremental (UF-062) | new filing → published candidate rows < 24 h |
| Clean rebuild from pinned manifest | < 14 days, no manual steps |
| PIT query (UF-016 target) | representative `as_of` snapshot < 10 s on one host |

## Cost assumptions

Single existing workstation (16 cores / 14 GB / NVMe): no incremental
hardware cost for compute. **Disk is the one confirmed purchase**: 257 GB
free today vs. ≈1.2–1.7 TB measured Bronze requirement — a ~2 TB drive
(~$150–300) must be installed before UF-023 runs at scale; this belongs on
UF-023's checklist. SEC data is free; no licensed data in Release 1. LLM
review-packet costs are deferred to UF-042/043 sizing. Object storage at
~$0.005–0.023/GB·mo (~$10–40/mo for ~1.7 TB) remains the ADR-0001 fallback.

## Revision log

| Date | Change |
| --- | --- |
| 2026-07-25 | Initial provisional estimates (pre-measurement) |
| 2026-07-25 | UF-010A revision: measured closure size, parse time, RSS, request budget from 67 real accessions; added the 2010–2011 XBRL-cliff finding; disk purchase confirmed as the binding cost |
