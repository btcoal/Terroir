# Execution Backlog: Point-in-Time U.S. Fundamentals

This backlog converts `thesis.md`, `antithesis.md`, and `synthesis.md` into an
execution sequence for Release 1.

## Release 1 boundary

Release 1 covers domestic operating companies that file U.S.-GAAP 10-K,
10-Q, 10-K/A, and 10-Q/A forms. It produces point-in-time data from the cover
page and primary financial statements:

- balance sheet;
- income statement;
- comprehensive income statement;
- cash-flow statement;
- shareholders' equity statement where required.

Release 1 does not include detailed footnote extraction, segment schedules,
debt maturities, pension tables, tax footnotes, a market-price database,
imputation, or silent FX conversion. Banks, insurers, REITs, utilities,
investment companies, shell companies, and asset-backed issuers remain
excluded until their accounting schemas and QC rules are explicitly added.

The public identifier product is named **SEC-to-market-security linking**.
CRSP, Compustat, licensed CUSIP, and similar mappings are optional adapters,
not foundations of the public data model.

## Planning conventions

- Priority: `P0` blocks Release 1, `P1` is required for production operation,
  and `P2` is a documented follow-on.
- Size: `S` is up to two engineering days, `M` is roughly three to five days,
  and `L` is roughly one to two weeks. Sizes are relative and should be
  recalibrated after UF-005.
- A ticket is complete only when its code, tests, schema or documentation,
  migration when applicable, and operational diagnostics are committed
  together.
- No failed or quarantined observation may be silently dropped from Bronze or
  Silver.

## Execution order

```text
Scope and contracts
        |
        v
Correctness and storage foundations
        |
        v
Acquisition --> Silver parsing --> Security master
                       |                  |
                       +--------+---------+
                                v
                    Gold mapping and PIT engine
                                |
                                v
                       QC and Research layer
                                |
                                v
                       Backfill and release
```

## Milestones

| Milestone | Exit condition |
| --- | --- |
| M0 — Product contract | Scope, ontology, time policy, identifiers, and architecture are frozen |
| M1 — Correctness foundation | Schemas, manifests, offline taxonomies, logical hashing, and PIT invariant tests exist |
| M2 — Bronze and Silver | The target accession set can be acquired, reconciled, parsed, and reproduced |
| M3 — Security master | Temporal entity, security, and listing histories are queryable with evidence |
| M4 — Gold and PIT | Core metrics, filing versions, comparability bases, and PIT views work end to end |
| M5 — QC and Research | Quarantine, validation, derived metrics, and research tests satisfy thresholds |
| M6 — Release and operation | The historical release is published and incremental operation is observable |

---

Ticket specifications are canonical in [`tickets/`](tickets/). This file
retains the release boundary, execution order, milestone index, and release
gates.

---

## M0 — Product contract

| Ticket | Priority / size | Depends on |
| --- | --- | --- |
| [UF-001 — Freeze the Release 1 charter and issuer universe](tickets/UF-001.md) | P0 / M | None |
| [UF-002 — Publish the versioned canonical data dictionary](tickets/UF-002.md) | P0 / L | UF-001 |
| [UF-003 — Specify information availability and execution-time policies](tickets/UF-003.md) | P0 / M | UF-001 |
| [UF-004 — Define the fundamentals-to-returns and identifier contracts](tickets/UF-004.md) | P0 / M | UF-001 |
| [UF-005 — Record architecture decisions and recalibrate the backlog](tickets/UF-005.md) | P0 / M | UF-001, UF-002, UF-003, UF-004 |

---

## M1 — Correctness and storage foundations

| Ticket | Priority / size | Depends on |
| --- | --- | --- |
| [UF-010 — Scaffold the repository, CI, configuration, and observability](tickets/UF-010.md) | P0 / M | UF-005 |
| [UF-011 — Implement versioned schemas and migrations](tickets/UF-011.md) | P0 / L | UF-002, UF-003, UF-004, UF-010 |
| [UF-012 — Build immutable parser-input storage and accession manifests](tickets/UF-012.md) | P0 / M | UF-010, UF-011 |
| [UF-013 — Build and pin the offline taxonomy package cache](tickets/UF-013.md) | P0 / L | UF-012 |
| [UF-014 — Implement deterministic build manifests and logical hashing](tickets/UF-014.md) | P0 / M | UF-010, UF-011, UF-012, UF-013 |
| [UF-015 — Create synthetic fixtures and PIT metamorphic test harness](tickets/UF-015.md) | P0 / L | UF-003, UF-010, UF-011, UF-014 |
| [UF-016 — Benchmark and select Parquet/DuckDB physical layouts](tickets/UF-016.md) | P0 / M | UF-011, UF-014 |

---

## M2 — Bronze acquisition and Silver parsing

| Ticket | Priority / size | Depends on |
| --- | --- | --- |
| [UF-020 — Implement a policy-compliant SEC transport client](tickets/UF-020.md) | P0 / M | UF-010 |
| [UF-021 — Build the target universe and expected accession inventory](tickets/UF-021.md) | P0 / L | UF-001, UF-020 |
| [UF-022 — Ingest SEC bulk reconciliation datasets](tickets/UF-022.md) | P0 / M | UF-020, UF-021 |
| [UF-023 — Acquire and validate raw filing parser inputs](tickets/UF-023.md) | P0 / L | UF-012, UF-020, UF-021 |
| [UF-024 — Reconcile acquisition completeness](tickets/UF-024.md) | P0 / M | UF-021, UF-022, UF-023 |
| [UF-025 — Implement the supervised Arelle worker pool](tickets/UF-025.md) | P0 / L | UF-013, UF-023 |
| [UF-026 — Extract complete Silver XBRL structures](tickets/UF-026.md) | P0 / L | UF-011, UF-025 |
| [UF-027 — Add parser, EFM, DQC, and source-reconciliation QC](tickets/UF-027.md) | P0 / L | UF-022, UF-026 |

---

## M3 — Temporal entity and security master

| Ticket | Priority / size | Depends on |
| --- | --- | --- |
| [UF-030 — Build temporal entity records from SEC evidence](tickets/UF-030.md) | P0 / M | UF-021, UF-026 |
| [UF-031 — Parse dimensional cover-page security observations](tickets/UF-031.md) | P0 / M | UF-026, UF-030 |
| [UF-032 — Extract pre-tagging and untagged listing evidence](tickets/UF-032.md) | P0 / L | UF-020, UF-023, UF-030 |
| [UF-033 — Infer securities and temporal listing intervals](tickets/UF-033.md) | P0 / L | UF-004, UF-031, UF-032 |
| [UF-034 — Add security-master QC and optional identifier adapters](tickets/UF-034.md) | P1 / M | UF-033 |

---

## M4 — Gold mapping, periodization, and PIT

| Ticket | Priority / size | Depends on |
| --- | --- | --- |
| [UF-040 — Implement the versioned mapping-rule schema and compiler](tickets/UF-040.md) | P0 / L | UF-002, UF-011, UF-026 |
| [UF-041 — Implement deterministic standard-concept mappings](tickets/UF-041.md) | P0 / L | UF-027, UF-040 |
| [UF-042 — Enforce strict schemas for all machine-consumed LLM output](tickets/UF-042.md) | P0 / M | UF-002, UF-040 |
| [UF-043 — Build custom-concept proposals and human review packets](tickets/UF-043.md) | P0 / L | UF-027, UF-040, UF-042 |
| [UF-044 — Build canonical fact selection with complete provenance](tickets/UF-044.md) | P0 / L | UF-041, UF-043, UF-045 |
| [UF-045 — Implement fiscal-period classification](tickets/UF-045.md) | P0 / L | UF-002, UF-026 |
| [UF-046 — Derive compatible standalone quarters](tickets/UF-046.md) | P0 / M | UF-044, UF-045 |
| [UF-047 — Classify amendment scope and build filing version chains](tickets/UF-047.md) | P0 / L | UF-026, UF-044 |
| [UF-048 — Model comparability events and accounting bases](tickets/UF-048.md) | P0 / L | UF-044, UF-047 |
| [UF-049 — Implement as-filed, latest, and PIT resolution](tickets/UF-049.md) | P0 / L | UF-014, UF-015, UF-016, UF-044, UF-047, UF-048 |

---

## M5 — QC and Research layer

| Ticket | Priority / size | Depends on |
| --- | --- | --- |
| [UF-050 — Implement unified QC status and quarantine](tickets/UF-050.md) | P0 / L | UF-027, UF-044, UF-049 |
| [UF-051 — Implement accounting and cross-statement checks](tickets/UF-051.md) | P0 / L | UF-002, UF-044, UF-050 |
| [UF-052 — Implement exact cross-source reconciliation](tickets/UF-052.md) | P0 / M | UF-022, UF-044, UF-050 |
| [UF-053 — Add temporal, vintage, and currency QC](tickets/UF-053.md) | P0 / L | UF-045, UF-048, UF-050 |
| [UF-054 — Implement versioned derived fundamentals](tickets/UF-054.md) | P0 / L | UF-002, UF-046, UF-048, UF-050, UF-051 |
| [UF-055 — Implement session-aware research eligibility](tickets/UF-055.md) | P0 / M | UF-003, UF-049 |
| [UF-056 — Complete and score the human-audited golden corpus](tickets/UF-056.md) | P0 / L | UF-027, UF-033, UF-044, UF-047, UF-048 |
| [UF-057 — Run end-to-end research validation](tickets/UF-057.md) | P0 / L | UF-033, UF-049, UF-054, UF-055, UF-056 |

---

## M6 — Historical release and production operation

| Ticket | Priority / size | Depends on |
| --- | --- | --- |
| [UF-060 — Execute and reconcile the historical backfill](tickets/UF-060.md) | P0 / L | UF-024, UF-027, UF-033, UF-049, UF-050, UF-054 |
| [UF-061 — Enforce release gates and publish the release report](tickets/UF-061.md) | P0 / L | UF-014, UF-024, UF-051, UF-052, UF-056, UF-057, UF-060 |
| [UF-062 — Implement nightly incremental ingestion](tickets/UF-062.md) | P1 / L | UF-060, UF-061 |
| [UF-063 — Add production dashboards and alerts](tickets/UF-063.md) | P1 / M | UF-060, UF-062 |
| [UF-064 — Automate rebuilds and taxonomy/mapping governance](tickets/UF-064.md) | P1 / L | UF-061, UF-062, UF-063 |

---

## Explicit follow-on tickets, not Release 1

These items should not be pulled into a Release 1 ticket as incidental scope:

### UF-070 — Add specialist issuer accounting schemas

**Priority / size:** P2 / L

**Depends on:** UF-002, UF-040, UF-050, UF-056, UF-061

**Outcome:** A later release supports banks, insurers, REITs, utilities, and
investment companies through explicit sector-specific ontologies, mappings,
derived metrics, and QC rules without weakening the ordinary-operating-company
contract or silently reclassifying Release 1 history.

**Acceptance criteria:**

- Before implementation begins, the work is split into one independently
  releasable child ticket per issuer class and each child is resized using the
  evidence and conventions established by UF-005; UF-070 closes only when all
  five child tickets are complete.
- A new release charter and executable eligibility-policy version identify the
  supported issuer classes and the applicable accounting-schema version;
  Release 1 classifications and outputs remain immutable.
- The canonical dictionary defines sector applicability and separate reported
  and derived metrics for bank credit and deposit activity, insurance premiums
  and reserves, REIT property operations and funds from operations, regulated
  utility balances, and investment-company portfolios and net asset value.
- Mapping rules are versioned by issuer class and taxonomy vintage, reject
  cross-sector fallbacks, and preserve every source fact, context, unit,
  dimension, accession, and comparability basis.
- Sector-specific accounting identities, cross-statement checks, materiality
  thresholds, derived formulas, and quarantine rules are documented and
  executable; a generic Release 1 QC rule cannot override a valid specialist
  presentation.
- The audited golden corpus includes representative annual, quarterly, and
  amended filings for every issuer class across early and current taxonomy
  vintages, custom-tag rates, fiscal calendars, and material reporting
  patterns.
- Each issuer class meets approved precision, coverage, provenance,
  reconciliation, and zero-PIT-leakage gates before that class is published;
  failure by one class does not authorize or block publication of another.
- Research outputs expose sector applicability and definition versions so
  users cannot compare incompatible ordinary-company and specialist metrics
  without an explicit policy.
- Backfill, incremental ingestion, release reports, dashboards, and alerts are
  segmented by issuer class and accounting-schema version.

The remaining follow-ons are:

- detailed XBRL footnote and unstructured-text extraction;
- segment, geography, lease, debt-maturity, pension, and tax-note schemas;
- a survivorship-free prices, returns, and corporate-actions product;
- licensed CRSP, Compustat, or CUSIP adapters;
- point-in-time FX translation and currency-normalized research values;
- automated imputation;
- wide feature marts beyond those justified by measured workloads;
- distribution of Arelle behind a network service before load tests show it is
  needed.

## Release 1 definition of done

Release 1 is complete only when UF-001 through UF-061 are complete and:

1. every displayed value can identify its filing location, mapping rationale,
   availability time, and QC results;
2. later filings, amendments, mappings, and ticker changes cannot alter an
   earlier PIT snapshot;
3. the source manifest can reproduce a logically equivalent dataset;
4. the release report meets the stated acquisition, precision, coverage, and
   zero-leakage gates;
5. the market-data boundary is explicit and no Release 1 result implies that
   survivorship-free returns have already been solved.
