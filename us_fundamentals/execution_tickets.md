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

## M0 — Product contract

### UF-001 — Freeze the Release 1 charter and issuer universe

**Priority / size:** P0 / M  
**Depends on:** None

**Outcome:** A versioned charter gives ingestion, mapping, and release jobs one
deterministic definition of an eligible filing.

**Acceptance criteria:**

- The charter specifies supported forms, accounting standard, issuer types,
  start-date policy, primary statements, and explicit exclusions.
- Issuer eligibility is represented as executable configuration rather than
  prose alone.
- The configuration distinguishes unsupported issuers from missing or failed
  ingestion.
- The early-vintage policy allows a metric to have a later supported start
  year when empirical quality warrants it.
- A fixture demonstrates the expected decision for each inclusion and
  exclusion category.

### UF-002 — Publish the versioned canonical data dictionary

**Priority / size:** P0 / L  
**Depends on:** UF-001

**Outcome:** Every Release 1 canonical and derived metric has an unambiguous,
machine-readable contract before mapping implementation begins.

**Acceptance criteria:**

- The dictionary defines metric ID, name, statement, period type, unit,
  polarity, dimensional scope, industry applicability, and materiality tier.
- The core set includes `income_from_continuing_operations`,
  `income_from_discontinued_operations`, `net_income_total`,
  `net_income_attributable_to_parent`,
  `net_income_attributable_to_noncontrolling_interests`,
  `preferred_equity`, `preferred_dividends`,
  `redeemable_preferred_equity`, and `temporary_equity`.
- Book-equity variants have separate definitions, including
  `book_equity_reported`, `book_equity_common`, `book_equity_fama_french`, and
  `tangible_common_equity`.
- Reported, reconstructed, and adjusted definitions such as EBITDA are
  separate metrics with explicit formulas and fallback rules.
- The dictionary has a schema version and a validation command that rejects
  duplicate IDs, invalid enums, and incomplete definitions.

### UF-003 — Specify information availability and execution-time policies

**Priority / size:** P0 / M  
**Depends on:** UF-001

**Outcome:** Filing information time is separated from strategy-dependent
trading eligibility.

**Acceptance criteria:**

- Gold defines `sec_acceptance_datetime`, `information_available_at`,
  `observed_first_seen_at`, `availability_method`,
  `availability_policy_version`, and `availability_confidence`.
- The backfill policy uses a configurable dissemination buffer and records the
  applied policy version.
- The Research contract defines `eligible_session`, `eligible_at_open`,
  `eligible_at_close`, and `execution_policy_version`.
- The calendar contract covers time zones, daylight-saving changes, holidays,
  half-days, and unscheduled closures.
- Boundary examples cover filings before open, during a session, just before
  close, after close, after 5:30 p.m. Eastern, and on non-session days.

### UF-004 — Define the fundamentals-to-returns and identifier contracts

**Priority / size:** P0 / M  
**Depends on:** UF-001

**Outcome:** Fundamentals can join safely to a future survivorship-free market
dataset without claiming to implement that dataset in Release 1.

**Acceptance criteria:**

- The `market_observation` interface specifies prices, volume, raw close,
  split factor, dividends, total return, market cap, source availability,
  version, and QC status.
- The join key is the internal `security_id`, constrained by temporal listing
  validity.
- The contract specifies delisted-security retention, delisting-return policy,
  corporate-action lineage, and exchange calendar requirements.
- The public identifier hierarchy uses internal security ID, optional FIGI,
  CIK, historical ticker, exchange, title, and share class.
- PERMNO, PERMCO, GVKEY, IID, and licensed CUSIP are documented only as
  optional adapters.

### UF-005 — Record architecture decisions and recalibrate the backlog

**Priority / size:** P0 / M  
**Depends on:** UF-001, UF-002, UF-003, UF-004

**Outcome:** Implementation starts from explicit component boundaries and
measured assumptions.

**Acceptance criteria:**

- ADRs cover Bronze object storage, Silver and Gold formats, PostgreSQL
  metadata, DuckDB access, orchestration, process-isolated Arelle workers, and
  dataset versioning.
- The Arelle ADR chooses a supervised local process pool by default and names
  the measured condition that would justify a network microservice.
- The storage ADR mandates immutable parser-input closure and logical—not
  byte-level—dataset equivalence.
- The team records expected data volume, compute envelope, service-level
  objective, and cost assumptions.
- Every remaining ticket is reviewed for scope, ordering, and size; oversized
  tickets are split before work begins.

---

## M1 — Correctness and storage foundations

### UF-010 — Scaffold the repository, CI, configuration, and observability

**Priority / size:** P0 / M  
**Depends on:** UF-005

**Outcome:** All later components share typed configuration, repeatable local
commands, and baseline engineering controls.

**Acceptance criteria:**

- The repository has locked dependencies, formatter, linter, type checker,
  unit and integration test commands, and a CI workflow.
- Configuration is typed and supports isolated development, test, backfill,
  and production profiles without committed secrets.
- Structured logs include run ID, dataset version, accession where relevant,
  component, duration, and outcome.
- Retryable and terminal errors use distinct typed categories.
- A clean checkout can run the test suite and a minimal local pipeline from
  documented commands.

### UF-011 — Implement versioned schemas and migrations

**Priority / size:** P0 / L  
**Depends on:** UF-002, UF-003, UF-004, UF-010

**Outcome:** Bronze metadata, Silver facts, Gold observations, security master,
review state, QC results, and Research lineage have enforceable schemas.

**Acceptance criteria:**

- Migrations create entity, security, listing, filing, raw fact, context, unit,
  taxonomy relationship, mapping rule, canonical observation, comparability
  event, QC result, and dataset-release metadata.
- Filing time fields follow UF-003; raw facts retain `decimals`, nullable
  `precision`, dimensions, source document, and source location.
- Canonical observations retain accession, source concept/context, mapping
  rule, mapping confidence, derivation type, currency, QC status, and dataset
  version.
- Primary keys and uniqueness constraints prevent unresolved duplicate
  canonical versions while preserving duplicate raw facts for diagnosis.
- Forward and rollback migration tests pass against an empty and a populated
  test database.

### UF-012 — Build immutable parser-input storage and accession manifests

**Priority / size:** P0 / M  
**Depends on:** UF-010, UF-011

**Outcome:** Each accession has a reproducible, content-addressed parser input
closure without requiring storage of every irrelevant exhibit.

**Acceptance criteria:**

- The required closure includes filing index, primary or Inline XBRL document,
  instance, extension schema, consumed linkbases, labels, references, filing
  header, and every external document consumed by the parser.
- Each stored object records source path or URL, size, SHA-256, retrieval time,
  and content type.
- The accession manifest distinguishes stored, optional cold, and
  reference-only files.
- Reacquiring identical bytes is idempotent and a hash mismatch creates a
  terminal integrity event without overwriting the prior object.
- A fixture accession can be restored exclusively from its manifest and
  stored objects with network access disabled.

### UF-013 — Build and pin the offline taxonomy package cache

**Priority / size:** P0 / L  
**Depends on:** UF-012

**Outcome:** Historical parsing resolves standard taxonomy resources offline.

**Acceptance criteria:**

- The cache contains every taxonomy version referenced by the target universe,
  including `us-gaap`, `dei`, `srt`, `country`, `currency`, `exch`, `stpr`,
  document/entity, role, and reference schemas.
- Resources are installed as XBRL Taxonomy Packages with an offline URI
  catalog; filing extensions remain in accession storage.
- Package name, version, SHA-256, and URI catalog SHA-256 are included in build
  manifests.
- Normal parsing fails closed on an attempted network taxonomy resolution and
  emits the unresolved URI.
- An offline test loads representative taxonomy vintages from the earliest,
  middle, and latest supported years.

### UF-014 — Implement deterministic build manifests and logical hashing

**Priority / size:** P0 / M  
**Depends on:** UF-010, UF-011, UF-012, UF-013

**Outcome:** The same pinned inputs and rules produce a provably equivalent
logical dataset.

**Acceptance criteria:**

- A release manifest records accession set, raw hashes, taxonomy packages,
  parser version, mapping version, QC-rule version, formula version, code
  commit, and build timestamp.
- Logical hashes normalize row order, numeric representation, timestamps,
  nulls, and primary-key serialization.
- Equivalent datasets written with different Parquet row groups or compression
  settings produce the same logical hash.
- A one-value, one-timestamp, or one-lineage change produces a different hash.
- Full and incremental builds over the same pinned inputs can be compared with
  one command that reports row-level differences.

### UF-015 — Create synthetic fixtures and PIT metamorphic test harness

**Priority / size:** P0 / L  
**Depends on:** UF-003, UF-010, UF-011, UF-014

**Outcome:** Point-in-time invariants exist before any Gold transformation is
eligible to merge.

**Acceptance criteria:**

- Fixtures cover original filings, later comparatives, financial and
  nonfinancial amendments, future filings, mapping-version changes, multiple
  share classes, ticker changes, and delistings.
- Calendar fixtures cover cutoffs, weekends, holidays, half-days, DST, and
  unscheduled closures.
- Fiscal fixtures cover YTD values, 52/53-week years, fiscal-year changes,
  transition periods, stubs, and incompatible bases.
- The harness asserts
  `logical_hash(D_t(F_<=t)) == logical_hash(D_t(F_<=T))` for `T > t`.
- Tests fail when a later amendment, restatement, mapping release, or current
  ticker is injected into an earlier snapshot.
- CI exposes PIT leakage as a dedicated hard-failure job with a required count
  of zero.

### UF-016 — Benchmark and select Parquet/DuckDB physical layouts

**Priority / size:** P0 / M  
**Depends on:** UF-011, UF-014

**Outcome:** Physical layout is selected from representative PIT and
cross-sectional workloads rather than intuition.

**Acceptance criteria:**

- Candidate long-table layouts partition by available or filing year and
  optionally metric group.
- Benchmarks compare sorting with `metric_id, entity_id, available_at,
  fiscal_period_end` against a company-history projection.
- The test includes an effective-interval table with `valid_from` and
  `valid_to`, plus representative `as_of` queries.
- Results report scanned rows/bytes, wall time, storage size, and incremental
  write cost on realistic cardinality.
- The selected layout and row-group sizing are recorded in an ADR with
  reproducible benchmark code.

---

## M2 — Bronze acquisition and Silver parsing

### UF-020 — Implement a policy-compliant SEC transport client

**Priority / size:** P0 / M  
**Depends on:** UF-010

**Outcome:** All SEC acquisition uses one cached, identified, throttled, and
observable transport.

**Acceptance criteria:**

- The client requires a declared user agent and administrative contact.
- Aggregate request rate is capped below ten requests per second across all
  workers and honors retry/backoff signals.
- Conditional requests, cache hits, retries, response size, status, and
  content hash are logged.
- Bulk archives are preferred for historical initialization and per-accession
  requests are deduplicated.
- Tests simulate rate limiting, partial content, malformed responses, retries,
  and restart after interruption.

### UF-021 — Build the target universe and expected accession inventory

**Priority / size:** P0 / L  
**Depends on:** UF-001, UF-020

**Outcome:** The project has a versioned denominator for acquisition coverage.

**Acceptance criteria:**

- Bulk submissions and daily/quarterly indexes produce a normalized accession
  inventory for eligible forms and issuers.
- Each accession records CIK, form, amendment flag, report period, filing date,
  SEC acceptance datetime, and discovery sources.
- Conflicts among discovery sources are retained and classified.
- Eligibility decisions reference the executable Release 1 policy and never
  discard excluded rows from the inventory.
- Rebuilding from the same source snapshots produces the same inventory
  logical hash.

### UF-022 — Ingest SEC bulk reconciliation datasets

**Priority / size:** P0 / M  
**Depends on:** UF-020, UF-021

**Outcome:** Company Facts and Financial Statement Data Sets are locally
available as independent checks, not authoritative replacements for filings.

**Acceptance criteria:**

- Bulk Submissions, Company Facts, and quarterly Financial Statement Data Sets
  are ingested with source version, retrieval time, and checksums.
- Source rows retain accession, concept, unit, period, dimensions or segment
  where available, and the upstream dataset vintage.
- Loading is idempotent and supports append-only arrival of a new source
  vintage.
- The Notes dataset is not transformed into Release 1 Gold metrics.
- Coverage reports join each bulk source to the expected accession inventory.

### UF-023 — Acquire and validate raw filing parser inputs

**Priority / size:** P0 / L  
**Depends on:** UF-012, UF-020, UF-021

**Outcome:** Every target accession is either reproducibly acquired or has an
explicit terminal reason.

**Acceptance criteria:**

- The job discovers and stores the parser input closure defined by UF-012.
- It verifies file presence, size, hash, basic syntax, accession-to-CIK
  ownership, and duplicate ingestion.
- Work is checkpointed at accession and object level and resumes without
  redownloading valid content.
- A missing, malformed, or inconsistent input receives a classified state and
  remains retryable or terminal according to policy.
- Download logs and manifests are immutable and tied to a run and dataset
  version.

### UF-024 — Reconcile acquisition completeness

**Priority / size:** P0 / M  
**Depends on:** UF-021, UF-022, UF-023

**Outcome:** Missing coverage is measurable and explainable before parsing
begins at scale.

**Acceptance criteria:**

- A report compares acquired accessions to daily/quarterly indexes,
  Submissions histories, bulk archives, and expected form sequences.
- Every expected accession is classified as acquired, excluded by policy,
  unavailable upstream, retry pending, or terminal failure.
- Duplicate, truncated, CIK-mismatched, and manifest-incomplete accessions are
  separately counted.
- Full and incremental acquisition over the same accession set produce the
  same raw manifest logical hash.
- The report exposes progress toward the 99.95% acquired-or-accounted-for
  Release 1 gate.

### UF-025 — Implement the supervised Arelle worker pool

**Priority / size:** P0 / L  
**Depends on:** UF-013, UF-023

**Outcome:** Arelle runs out of process in warm, bounded-lifetime workers
partitioned by taxonomy version.

**Acceptance criteria:**

- Workers preload offline taxonomy packages and accept filing-level jobs
  through a structured staging interface.
- Workers recycle after configurable filing-count or RSS thresholds and have
  filing-level timeouts.
- Output publication is atomic; a crash cannot expose partial Silver results.
- Structured diagnostics include taxonomy version, parse time, peak RSS,
  cache hit status, warnings, validation messages, and exit reason.
- Repeated crashes quarantine the filing after a bounded retry count.
- A load test records throughput, RSS behavior, failure rate, and taxonomy
  cache benefits across multiple vintages.

### UF-026 — Extract complete Silver XBRL structures

**Priority / size:** P0 / L  
**Depends on:** UF-011, UF-025

**Outcome:** Every parsed fact and its XBRL context can be reconstructed
without economic reinterpretation.

**Acceptance criteria:**

- Silver stores raw facts, contexts, units, dimensions, period data, nil state,
  raw and numeric values, decimals, nullable precision, and source locations.
- Presentation, calculation, definition, label, and reference relationships
  are retained with role and order/weight metadata.
- Standard and filer-extension QNames and namespaces remain distinguishable.
- Duplicate facts and inconsistent duplicates are retained and classified
  rather than collapsed silently.
- Reprocessing an accession is idempotent for the same parser and taxonomy
  versions.

### UF-027 — Add parser, EFM, DQC, and source-reconciliation QC

**Priority / size:** P0 / L  
**Depends on:** UF-022, UF-026

**Outcome:** Silver parse quality is independently measurable before canonical
mapping.

**Acceptance criteria:**

- All Arelle, XBRL 2.1, Inline XBRL, SEC EFM, dimensional, unit, duplicate,
  calculation, and effective DQC diagnostics are retained with pinned rule
  versions.
- A parser golden corpus compares fact counts, QNames, periods, dimensions,
  units, values, and source locations with reference output.
- Parsed standard facts reconcile to Company Facts and Financial Statement
  Data Sets on the strongest available keys.
- Mismatches use the documented classification taxonomy and unresolved
  discrepancies create review or quarantine records.
- Quality statistics are reported by form, filing year, taxonomy version, and
  issuer cohort.

---

## M3 — Temporal entity and security master

### UF-030 — Build temporal entity records from SEC evidence

**Priority / size:** P0 / M  
**Depends on:** UF-021, UF-026

**Outcome:** Legal filers have stable internal identities and time-varying
attributes.

**Acceptance criteria:**

- Entity records use internal IDs and CIK, with legal name, incorporation,
  fiscal year end, type, `valid_from`, and `valid_to`.
- Attribute changes retain source accession or source snapshot and confidence.
- Current SEC files seed state but never rewrite prior valid intervals.
- Mergers, reverse mergers, and name changes have fixtures that preserve
  historical identity and provenance.
- Unsupported entity types remain queryable and carry their exclusion reason.

### UF-031 — Parse dimensional cover-page security observations

**Priority / size:** P0 / M  
**Depends on:** UF-026, UF-030

**Outcome:** Tagged cover pages supply point-in-time evidence for one or many
listed securities per CIK.

**Acceptance criteria:**

- Silver-derived observations retain security title, trading symbol, exchange,
  security-axis member, shares outstanding, measurement date, accession, and
  availability.
- Multiple share classes and multiple symbols in one filing remain distinct.
- The implementation handles the 2019–2021 cover-page tagging phase-in and
  does not infer absence before mandate dates.
- Conflicting symbol/title/exchange contexts create diagnostics instead of a
  last-write-wins result.
- Fixtures cover single class, dual class, ticker change, exchange change, and
  missing tagged cover-page data.

### UF-032 — Extract pre-tagging and untagged listing evidence

**Priority / size:** P0 / L  
**Depends on:** UF-020, UF-023, UF-030

**Outcome:** Historical listing evidence before tagged cover pages is
normalized without pretending every source is equally authoritative.

**Acceptance criteria:**

- Extractors cover filing cover-page text, filing headers, archived SEC
  company-ticker snapshots, and available exchange symbol-directory snapshots.
- Registration, merger, spin-off, and delisting filings can contribute
  structured evidence.
- Each evidence row records source, observed time, asserted effective time,
  security title/class, symbol, exchange, and confidence.
- Optional external ticker-change archives are isolated behind adapters with
  source licensing metadata.
- Source conflicts are retained for interval inference and review.

### UF-033 — Infer securities and temporal listing intervals

**Priority / size:** P0 / L  
**Depends on:** UF-004, UF-031, UF-032

**Outcome:** Researchers can join a filing entity to the correct historical
security and listing without using ticker as a permanent identifier.

**Acceptance criteria:**

- The model supports one entity to many securities and one security to many
  listing intervals.
- Every inferred interval includes `valid_from`, `valid_to`, supporting
  evidence, inference-rule version, confidence, and review status.
- Overlapping intervals for the same security/exchange are rejected unless an
  explicit multi-listing rule permits them.
- Current evidence cannot rewrite a historical ticker in an archived snapshot.
- Inactive and delisted securities remain queryable.
- Golden fixtures cover ticker reuse by another issuer, dual-class issuers,
  exchange transfers, spin-offs, mergers, and delistings.

### UF-034 — Add security-master QC and optional identifier adapters

**Priority / size:** P1 / M  
**Depends on:** UF-033

**Outcome:** Security linkage quality is measured, and nonpublic identifiers
cannot contaminate the core public product.

**Acceptance criteria:**

- QC reports gaps, overlaps, low-confidence intervals, ticker collisions, and
  unexplained class changes.
- Optional FIGI resolution records request inputs, response version, observed
  time, confidence, and temporal validation.
- Licensed identifier adapters live in a separate namespace and can be
  disabled without changing public security IDs.
- Adapter results never overwrite source evidence or inferred interval
  history.
- Historical-universe tests prove that delisted names and old tickers survive
  rebuilds.

---

## M4 — Gold mapping, periodization, and PIT

### UF-040 — Implement the versioned mapping-rule schema and compiler

**Priority / size:** P0 / L  
**Depends on:** UF-002, UF-011, UF-026

**Outcome:** Approved semantic mappings compile into deterministic,
testable selection rules.

**Acceptance criteria:**

- Rules specify canonical metric, concept, taxonomy versions, forms, period
  type, units, dimensions, statement roles, sign treatment, priority,
  industry scope, status, and version.
- Rule states are `candidate`, `approved`, and `rejected`; only approved rules
  compile for production.
- The compiler rejects overlapping rules that can select the same fact at the
  same priority without an explicit tie-breaker.
- A rule is immutable after release; a change produces a new mapping version.
- Compiled rules carry their source rule ID into every canonical observation.

### UF-041 — Implement deterministic standard-concept mappings

**Priority / size:** P0 / L  
**Depends on:** UF-027, UF-040

**Outcome:** The Release 1 core metrics map from standard taxonomy concepts
without LLM involvement.

**Acceptance criteria:**

- Standard mappings cover every metric in the Release 1 data dictionary for
  supported taxonomy vintages where a standard concept exists.
- Rules enforce period type, unit, statement role, dimensions, taxonomy
  vintage, form, sign, and industry restrictions.
- High-materiality metrics have explicit source-priority and no silent
  fallback to weaker semantics.
- Tests cover concept renames, deprecated concepts, multiple candidates,
  dimensional facts, and valid absence.
- Mapping coverage and conflict counts are reported by metric, filing year,
  and taxonomy version.

### UF-042 — Enforce strict schemas for all machine-consumed LLM output

**Priority / size:** P0 / M  
**Depends on:** UF-002, UF-040

**Outcome:** An LLM can propose review artifacts but can never write malformed
or unconstrained data into durable queues.

**Acceptance criteria:**

- Provider-native schema-constrained generation is used where available, then
  every response passes local strict Pydantic or JSON Schema validation.
- Schemas forbid extra fields and require schema version, proposal ID,
  enumerated metric and transformation, confidence in `[0,1]`, evidence,
  alternatives, and review status.
- Semantic validation proves that cited concepts, contexts, units, period
  types, statement roles, and relationships exist in the source filing.
- Schema or semantic failure receives bounded retries followed by quarantine;
  no default mapping is improvised.
- LLM output has no production database write path except through the approved
  rule compiler.

### UF-043 — Build custom-concept proposals and human review packets

**Priority / size:** P0 / L  
**Depends on:** UF-027, UF-040, UF-042

**Outcome:** Unmapped custom concepts enter an auditable proposal, review, and
test-fixture workflow.

**Acceptance criteria:**

- Proposal evidence includes labels/definition, calculations, presentation,
  role, period, unit, balance, dimensions, neighbors, prior filer concepts,
  peers, and visible filing context.
- Review packets include issuer, accession, form, period, proposed mapping,
  alternatives, downstream effect, confidence, and failed QC rules.
- Reviewers can approve, reject, or modify a proposal with identity,
  timestamp, rationale, and mapping-version lineage.
- Each decision generates a regression fixture so the same ambiguity cannot
  recur silently.
- Automated promotion is disabled until metric-specific precision thresholds
  are demonstrated on a labeled sample.

### UF-044 — Build canonical fact selection with complete provenance

**Priority / size:** P0 / L  
**Depends on:** UF-041, UF-043, UF-045

**Outcome:** Deterministic selection turns eligible Silver facts into
traceable Gold observations without altering reported values.

**Acceptance criteria:**

- Selection applies rule priority, permitted scope, period, unit, role, and
  dimension filters deterministically.
- Every value retains accession, source fact/context, source concept, mapping
  rule, confidence, reported unit/currency, availability, and dataset version.
- Direct, aggregated, derived-quarter, TTM, standardized, manual override, and
  imputed derivations use distinct enums; Release 1 produces no imputed rows.
- Unresolved duplicate candidates are quarantined rather than selected
  arbitrarily.
- The engine never changes a raw reported value to make an identity balance.

### UF-045 — Implement fiscal-period classification

**Priority / size:** P0 / L  
**Depends on:** UF-002, UF-026

**Outcome:** Facts receive reliable fiscal periods without relying only on the
filing `fp` field or SEC calendar frames.

**Acceptance criteria:**

- Facts classify as instant, quarter, YTD, fiscal year, transition, or
  nonstandard duration using dates, fiscal year end, form, role, and context.
- The engine handles non-calendar years, 52/53-week years, fiscal-year changes,
  transition reports, IPO stubs, mergers, and reverse mergers.
- SEC frames are retained as evidence but are not the primary classifier.
- Fiscal period IDs are stable across filing versions presenting the same
  economic period.
- Ambiguous or overlapping period assignments emit review diagnostics.

### UF-046 — Derive compatible standalone quarters

**Priority / size:** P0 / M  
**Depends on:** UF-044, UF-045

**Outcome:** YTD facts produce standalone Q2, Q3, and Q4 only when their bases
are demonstrably compatible.

**Acceptance criteria:**

- The engine implements `Q2 = H1 - Q1`, `Q3 = 9M - H1`, and `Q4 = FY - 9M`.
- Inputs must share scope, dimensions, currency, fiscal year, compatible
  restatement/comparability basis, and contiguous dates.
- Reported cumulative and derived standalone observations remain separate and
  link to all source observations.
- Derived values carry formula version, derivation type, and propagated QC.
- Negative tests reject incompatible currency, basis, dimensions, and fiscal
  calendars.

### UF-047 — Classify amendment scope and build filing version chains

**Priority / size:** P0 / L  
**Depends on:** UF-026, UF-044

**Outcome:** A `/A` form becomes a financial revision only when its facts show
that it changed financial information.

**Acceptance criteria:**

- Each amendment links to the accession it amends where determinable.
- Types include nonfinancial Part III, cover-page only, primary statements,
  notes, exhibits only, XBRL correction, mixed, and unknown.
- The record includes changed raw and canonical fact counts, affected
  statements, method, confidence, and evidence.
- Version chains preserve original, amendment, later comparative, and latest
  values without overwriting any version.
- Revision statistics exclude nonfinancial amendments by default.
- Fixtures cover Part III amendments with no statement delta and financial
  amendments with one or multiple affected statements.

### UF-048 — Model comparability events and accounting bases

**Priority / size:** P0 / L  
**Depends on:** UF-044, UF-047

**Outcome:** Correct recast values remain distinguishable when business or
accounting basis changes make periods non-comparable.

**Acceptance criteria:**

- `comparability_event` records type, effective period, first filing,
  affected metrics, prior/new basis IDs, evidence, confidence, and review
  status.
- Initial event types include discontinued operations, reporting currency,
  fiscal calendar, major standard adoption, segment reorganization, reverse
  merger, fresh-start accounting, major acquisition, and major divestiture.
- Canonical observations can carry `comparability_basis_id` and
  `comparability_status`.
- Original-basis and later recast comparative values coexist with their own
  availability and provenance.
- Growth and quarter-derivation APIs reject cross-basis calculation by default
  and require an explicit override policy.

### UF-049 — Implement as-filed, latest, and PIT resolution

**Priority / size:** P0 / L  
**Depends on:** UF-014, UF-015, UF-016, UF-044, UF-047, UF-048

**Outcome:** Users can retrieve the value in one filing, the latest restated
value, or exactly what was knowable at an earlier timestamp.

**Acceptance criteria:**

- APIs or views implement `V_as_filed(accession)`, `V_latest(period)`, and
  `V_PIT(period, as_of)`.
- PIT selection uses `information_available_at`; it never uses research-layer
  execution eligibility as an information boundary.
- An effective-interval table materializes `valid_from` and `valid_to` for
  efficient PIT lookup.
- Filing-version lineage and mapping-version lineage remain independent and
  queryable.
- All UF-015 leakage and metamorphic tests pass with zero violations.
- Representative DuckDB queries meet the performance target established by
  UF-016.

---

## M5 — QC and Research layer

### UF-050 — Implement unified QC status and quarantine

**Priority / size:** P0 / L  
**Depends on:** UF-027, UF-044, UF-049

**Outcome:** Every canonical observation has an explainable usability state,
and hard failures cannot reach standard Research outputs.

**Acceptance criteria:**

- Statuses are Pass, Pass with warning, Review, Quarantined, and Rejected.
- Rule results retain rule/version, severity, observed inputs, residual or
  diagnostic, timestamp, and resolution lineage.
- Hard failures include malformed filing, unresolved canonical duplicate,
  incompatible units, impossible PIT time, accession/CIK mismatch, invalid
  rule scope, altered source value, required-identity failure, and missing
  provenance.
- Standard Research views exclude Quarantined and Rejected rows by default and
  expose simple overrides for audit work.
- The related raw and Silver facts remain queryable for every status.

### UF-051 — Implement accounting and cross-statement checks

**Priority / size:** P0 / L  
**Depends on:** UF-002, UF-044, UF-050

**Outcome:** Accounting identities produce rounding-aware evidence without
forcing source values to reconcile.

**Acceptance criteria:**

- Rules cover assets/liabilities/equity variants, gross profit, cash roll
  forward, and operating-income composition where compatible inputs exist.
- Cross-statement checks cover net income, cash, depreciation, shares,
  debt, PP&E, and EPS/earnings/share relationships applicable to Release 1.
- Tolerances derive from XBRL `decimals`, calculation weights, and a documented
  floating-point epsilon; infinite precision contributes zero rounding
  uncertainty.
- Each failure stores the formula, inputs, uncertainty bound, residual, and
  known definitional exception.
- No check repairs, deletes, or overwrites a reported fact.

### UF-052 — Implement exact cross-source reconciliation

**Priority / size:** P0 / M  
**Depends on:** UF-022, UF-044, UF-050

**Outcome:** Disagreement with SEC-derived datasets is classified and routed,
not hidden.

**Acceptance criteria:**

- Standard observations reconcile on accession, concept, unit, period, and
  dimensional scope where supported.
- Difference types include custom-concept exclusion, primary-statement
  selection, dimension exclusion, duplicate-context selection, taxonomy
  version, SEC extraction, internal defect, and unresolved.
- Unresolved material mismatches create quarantine and a review packet.
- Reports show mismatch rate and materiality by source, metric, filing year,
  taxonomy version, and issuer cohort.
- Resolution decisions become versioned regression fixtures.

### UF-053 — Add temporal, vintage, and currency QC

**Priority / size:** P0 / L  
**Depends on:** UF-045, UF-048, UF-050

**Outcome:** Time-series discontinuities, early-vintage risk, and currency
conflicts are visible and policy controlled.

**Acceptance criteria:**

- Checks detect overlaps, missing quarters, sequence breaks, fiscal-year
  changes, duplicates, sign reversals, unit changes, concept substitutions,
  and unusually large revisions.
- Outliers create warnings or review priority and never automatic value edits.
- Every quality report is stratified by filing year and taxonomy version, with
  larger audited samples for early vintages.
- Gold preserves reported currency and raw unit and performs no silent FX
  conversion.
- Conflicting consolidated currencies for one statement/period are
  quarantined unless dimensions explain them.
- Research-layer FX fields and point-in-time policy are schema-ready but may
  remain unpopulated in Release 1.

### UF-054 — Implement versioned derived fundamentals

**Priority / size:** P0 / L  
**Depends on:** UF-002, UF-046, UF-048, UF-050, UF-051

**Outcome:** Core research variables are calculated only from eligible,
compatible canonical inputs.

**Acceptance criteria:**

- Initial formulas include TTM revenue/earnings, book-equity variants, tangible
  book, debt/net debt, profitability, ROA/ROE, margins, accruals, asset and
  investment growth, sales/earnings growth, intensities, issuance/repurchase,
  leverage, cash-flow-to-assets, payout, and diluted-share growth.
- Every formula records version, required inputs, fallback hierarchy, industry
  exclusions, unit, expected domain, basis requirements, and PIT lag policy.
- Inputs must satisfy the formula's QC threshold and comparability-basis rule.
- Alternative accounting definitions remain separate output metrics.
- Every derived observation links to all canonical inputs and their dataset
  and formula versions.

### UF-055 — Implement session-aware research eligibility

**Priority / size:** P0 / M  
**Depends on:** UF-003, UF-049

**Outcome:** Daily and intraday research code can apply explicit execution lag
without mutating Gold information time.

**Acceptance criteria:**

- A versioned exchange calendar maps `information_available_at` to
  strategy-specific eligible sessions.
- The default daily policy selects the first session whose open occurs after
  information availability.
- Intraday policies require explicit processing and execution latency.
- Results store eligible session/open/close and execution-policy version.
- Tests cover all UF-003 boundary cases and prove that a near-close filing
  cannot enter that day's close-to-close feature set.

### UF-056 — Complete and score the human-audited golden corpus

**Priority / size:** P0 / L  
**Depends on:** UF-027, UF-033, UF-044, UF-047, UF-048

**Outcome:** Mapping, periodization, amendment, and security-linkage quality are
measured against visible filing evidence.

**Acceptance criteria:**

- The corpus contains several hundred stratified 10-K/10-Q filings and
  amendments across size, industry, custom-tag rate, calendar type, IPO/stub,
  merger/spin-off, and multiple-share-class cases.
- Each audited observation records expected metric, value, period, source
  location/concept, dimensions, acceptable alternatives, and auditor notes.
- Precision, recall, coverage, and confidence calibration are reported by
  metric, standard/custom concept, industry, size, filing year, and taxonomy
  version.
- The core-metric launch target is at least 99.5% estimated precision and 98%
  coverage for supported ordinary nonfinancial operating companies.
- Unrecognized custom concepts remain under manual review unless a
  metric-specific automated-promotion threshold is approved.

### UF-057 — Run end-to-end research validation

**Priority / size:** P0 / L  
**Depends on:** UF-033, UF-049, UF-054, UF-055, UF-056

**Outcome:** The dataset is validated through realistic cross-sectional
research rather than only field-level checks.

**Acceptance criteria:**

- PIT signals include book-to-market, gross and operating profitability,
  asset growth, accruals, investment, earnings yield, sales growth, issuance,
  and leverage.
- Reports show coverage, missingness by size/industry, distributions through
  time, and sensitivity to warning and low-confidence exclusions.
- Archived PIT snapshots reconstruct the same signal inputs after a rebuild.
- Factor or portfolio results are stable under the documented rebuild
  tolerance and do not collapse when suspect observations are excluded.
- Optional vendor comparisons classify disagreements by definition, period,
  timing, vendor adjustment, security linkage, internal/vendor error, or
  unresolved; agreement is not optimized blindly.

---

## M6 — Historical release and production operation

### UF-060 — Execute and reconcile the historical backfill

**Priority / size:** P0 / L  
**Depends on:** UF-024, UF-027, UF-033, UF-049, UF-050, UF-054

**Outcome:** The complete Release 1 universe is processed through Bronze,
Silver, Gold, and Research with restartable operations.

**Acceptance criteria:**

- Backfill work is partitioned, checkpointed, idempotent, and restartable at
  accession and transformation stages.
- Operational reports show throughput, backlog, retry counts, failures,
  quarantine, storage, memory, and cost by filing vintage.
- Every expected accession is acquired or explicitly accounted for.
- Failed and repeatedly crashing filings have retained diagnostics and review
  ownership.
- Output tables and manifests are pinned to one candidate dataset version.

### UF-061 — Enforce release gates and publish the release report

**Priority / size:** P0 / L  
**Depends on:** UF-014, UF-024, UF-051, UF-052, UF-056, UF-057, UF-060

**Outcome:** A release can be published only through automated, inspectable
quality gates.

**Acceptance criteria:**

- At least 99.95% of expected accessions are acquired or explicitly accounted
  for, and every stored raw object has a checksum and manifest.
- Parser golden-corpus agreement, provenance completeness, uniqueness,
  zero PIT leakage, mapping precision, accounting QC, and source mismatch
  classification gates pass.
- A clean rebuild from the pinned manifest produces the same logical dataset
  hash.
- Quarantined and low-confidence data are removable with documented query
  flags.
- The human-readable report states universe, methods, versions, coverage,
  vintage quality, exclusions, known gaps, quarantine counts, and changes from
  prior releases.
- A failed gate blocks publication and links to the actionable diagnostics.

### UF-062 — Implement nightly incremental ingestion

**Priority / size:** P1 / L  
**Depends on:** UF-060, UF-061

**Outcome:** Newly disseminated filings move through the same reproducible
pipeline without weakening historical guarantees.

**Acceptance criteria:**

- The job discovers new filings, records `observed_first_seen_at`, acquires
  inputs, parses, maps, validates, and publishes an incremental dataset
  version.
- Replays and duplicate discovery are idempotent.
- Late amendments and comparative restatements extend version chains without
  mutating archived PIT outputs.
- A failed accession is isolated and does not make a partial release visible.
- Incremental output over a fixed accession set is logically equivalent to a
  full rebuild over that set.

### UF-063 — Add production dashboards and alerts

**Priority / size:** P1 / M  
**Depends on:** UF-060, UF-062

**Outcome:** Acquisition, parsing, mapping, quality, and drift failures become
operationally actionable.

**Acceptance criteria:**

- Dashboards show freshness, expected/observed filings, queue age, throughput,
  retry/failure rate, parser time/RSS, quarantine, mapping coverage, and QC
  drift.
- Alerts cover missing expected filings, repeated parser crashes, taxonomy
  resolution attempts, PIT violations, release-gate failures, and abnormal
  coverage changes.
- Every alert links to run, accession or release context and a documented
  response procedure.
- Alert thresholds are versioned and tested with synthetic failures.
- Metrics can be segmented by form, filing year, taxonomy version, and issuer
  cohort.

### UF-064 — Automate rebuilds and taxonomy/mapping governance

**Priority / size:** P1 / L  
**Depends on:** UF-061, UF-062, UF-063

**Outcome:** Full rebuilds and rule updates follow a controlled, reversible,
and auditable release process.

**Acceptance criteria:**

- A scheduled full rebuild can run from a pinned manifest in an isolated
  output namespace.
- Taxonomy updates are fetched into a new offline package version, tested
  across affected vintages, and never replace a pinned package in place.
- Mapping corrections create new rule and dataset versions and report the
  exact affected observations and research features.
- Candidate and production releases have an explicit promotion and rollback
  procedure.
- Archived PIT snapshots, release manifests, logical hashes, reports, and
  decision history are retained according to a documented policy.

---

## Explicit follow-on tickets, not Release 1

These items should not be pulled into a Release 1 ticket as incidental scope:

- detailed XBRL footnote and unstructured-text extraction;
- segment, geography, lease, debt-maturity, pension, and tax-note schemas;
- specialist accounting schemas for banks, insurers, REITs, and utilities;
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
