# UF-010A spike report: measured acquisition and parse figures

**Date:** 2026-07-25 · **Run:** `f7155006b406` · **Raw data:**
`.spike/measurements.jsonl` (not committed; regenerate with
`uv run python scripts/spike_uf010a.py`)

## What ran

67 accessions acquired across seven quarters (2010Q1, 2013Q2, 2016Q3,
2019Q4, 2022Q2, 2023Q4, 2025Q3), seeded-random within each quarter's
`form.idx`, plus Apple's FY2023 10-K as the guaranteed heavy large-
accelerated filer. Form mix: 17 × 10-K, 44 × 10-Q, 3 × 10-K/A, 3 × 10-Q/A.
Every closure was fetched through the production `SecTransport` (rate-capped,
cached, hash-logged); 56 filings parsed once each with Arelle in a fresh
subprocess. Total wall clock for selection + acquisition + parses: **174 s**.

## Headline findings

1. **The 2010 XBRL cliff is real and large.** 9 of 11 sampled 2010Q1
   filings — every non-large-accelerated filer in the sample — have **no
   XBRL objects at all** (mandate phase-in: large accelerated filers from
   mid-2009, all filers from mid-2011). The UF-001 filing-start of 2010
   therefore guarantees a structurally thin 2010–2011 vintage. UF-021 must
   report XBRL presence as an explicit inventory column, and the early-
   vintage metric policy in the charter will certainly be exercised, not
   hypothetically.
2. **Closures are smaller than assumed.** Median closure is ~2.0 MB across
   ~6 objects (p90 6.9 MB, max 33.7 MB — Southern Copper 10-K). The
   provisional 3–8 MB median estimate was roughly 2–4× high.
3. **Parse cost is dominated by taxonomy load, as ADR-0006 assumed.** With
   a cold Arelle web cache the first parse of a vintage took ~6 s; with the
   disk cache warm, fresh-process parses have median 0.6 s / p90 3.1 s /
   max 6.9 s. The arelle cache grew 22 → 193 files over the run and then
   stopped growing — per-vintage taxonomy sets are small and highly shared.
4. **Memory is a non-issue at this scale.** Peak RSS median 210 MB, max
   412 MB per parse process. The 1–4 GB/worker assumption was ~5–10× high;
   a 14 GB host supports 8–12 workers comfortably, not 4–6.

## Measured vs. assumed

| Quantity | Assumed (2026-07-25) | Measured |
| --- | --- | --- |
| Closure per accession (median) | 3–8 MB | **2.0 MB** (p90 6.9, max 33.7) |
| Objects per closure | — | median 6, max 7 |
| Parse time (median, warm disk cache) | 2–10 s | **0.6 s** (p90 3.1, max 6.9) |
| Peak RSS per parse | 1–4 GB | **0.21 GB** (max 0.41) |
| Facts per filing | — | median 740, p90 1,925, max 5,339 |
| Eligible 10-K/Q rows per quarter | — | 5,991–10,036 (declining trend) |

## Extrapolation to the Release 1 universe

Quarterly `form.idx` eligible-form counts from the six sampled quarters
average ≈ 7,900 rows/quarter (declining from ~9,400 in 2010 to ~6,000 in
2025). Over 66 quarters (2010 → mid-2026): **≈ 480k accessions** in the raw
denominator, before issuer-type exclusions and before the ~15–35% early-
vintage XBRL absence.

- **Bronze storage:** 480k × 3.6 MB mean ≈ **1.7 TB** upper bound; XBRL-
  bearing subset likely **1.2–1.5 TB**. Fits current local disk (257 GB
  free is NOT sufficient — a ~2 TB volume is required before UF-023 runs
  at scale; for this branch's bounded work it is a non-issue).
- **Acquisition requests:** ~480k × 7 objects ≈ 3.4M requests naively; bulk
  archives and the absence of XBRL in early vintages cut this
  substantially. At 8 rps sustained: **~5 days** of pure request time —
  half the assumed low end.
- **Parse compute:** 480k × ~1 s warm ≈ 133 CPU-hours; with supervision
  overhead and 8–12 workers, **parse is a sub-day to few-day problem, not
  10–40 days**. Acquisition, not parsing, is the wall-clock driver.

Error bars: single-host measurements, 56 parses, no >50 MB closures in
sample beyond one; large-filer inline documents (2023Q4 Apple: 4.6 MB,
3.1 s) suggest the right tail is manageable.

## Ticket-size review (per UF-010A acceptance criteria)

- UF-023 (L): stands, but the binding constraint is disk + request count,
  not parse compute. The pre-UF-023 disk purchase belongs on its checklist.
- UF-025 (L): worker-pool sizing simplifies (RSS small); load-test scope
  can shrink. Keep L for the supervision/atomicity work.
- UF-013 (L): vintage superset is small (≈170 cache files covered seven
  vintages); could be resized M at grooming.
- UF-021 (L): stands; add the XBRL-presence column requirement.
- UF-016, UF-011, UF-012, UF-014, UF-015, UF-020, UF-022, UF-024, UF-026,
  UF-027: no size change indicated by these measurements.

`assumptions.md` has been revised with these figures (see its revision log).
