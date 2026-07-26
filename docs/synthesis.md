These modifications materially improve the plan. I would adopt nearly all of them, with several refinements around timestamps, security identifiers, storage layout, and the exact role of Arelle. The strongest additions are the comparability-basis treatment, amendment-scope classification, offline taxonomy resolution, and explicit separation between a fundamentals product and a returns product. 

## 1. Availability and trading eligibility

The proposed separation is correct, though I would use three fields rather than centering `effective_trading_available_at` in the Gold layer:

```text
sec_acceptance_datetime
information_available_at
observed_first_seen_at
```

`sec_acceptance_datetime` is the unmodified EDGAR timestamp.

`information_available_at` is the historical availability estimate used for point-in-time data resolution. For backfills, this can be:

[
\text{information_available_at}
===============================

\text{sec_acceptance_datetime}
+
\text{dissemination buffer}.
]

`observed_first_seen_at` is populated prospectively by the live ingestion system. It provides an upper bound on when the system actually observed the filing, rather than claiming to know the exact historical dissemination time.

The SEC says filings are often available one to three minutes after the EDGAR timestamp, while some submissions begun after 5:30 p.m. Eastern can be disseminated on the next business day. That supports retaining a conservative, versioned availability policy rather than assuming the acceptance timestamp itself was tradable.

Execution eligibility belongs in the research layer:

```text
eligible_session
eligible_at_open
eligible_at_close
execution_policy_version
```

A research policy should map `information_available_at` to a market session using a versioned exchange calendar that handles holidays, half-days, daylight-saving changes, and unscheduled closures.

For a conservative daily close-to-close backtest:

[
\text{eligible session}
=======================

\text{first session whose open occurs after information_available_at}.
]

For an intraday strategy, the policy may instead use an explicit processing and execution latency.

I would therefore avoid a universal Gold-layer column called `effective_trading_available_at`. Its meaning necessarily depends on the strategy’s decision and execution schedule. A convenience `default_next_session` field is still useful for preventing accidental daily look-ahead.

Also add:

```text
availability_method
availability_policy_version
availability_confidence
```

Possible methods include `acceptance_plus_buffer`, `observed_first_seen`, and `manual_override`.

## 2. Arelle deployment model

The proposed process isolation is sensible. I would describe it as a **supervised, process-isolated worker pool**, leaving networked microservices optional.

A practical topology is:

```text
orchestrator
    |
    +-- queue: us-gaap-2022
    |       +-- warm Arelle worker processes
    |
    +-- queue: us-gaap-2023
    |       +-- warm Arelle worker processes
    |
    +-- queue: us-gaap-2024
            +-- warm Arelle worker processes
```

Each worker should:

* load an offline taxonomy package once;
* process a bounded number of filings;
* recycle after an RSS threshold or filing-count threshold;
* run with a filing-level timeout;
* write results through an atomic staging interface;
* return structured diagnostics;
* leave the filing quarantined after repeated crashes.

I would avoid placing an unqualified “Arelle leaks memory” assertion in the formal specification. Treat that as an operational risk to be measured. Add a backfill load test that records resident memory, parse duration, taxonomy cache hit rate, and failure rate by taxonomy vintage. Use those results to set the worker lifetime and memory budget.

A local subprocess pool is adequate for a single large machine. A containerized service becomes useful when parsing is distributed across nodes.

## 3. Structured LLM outputs

This change should be mandatory for every LLM response consumed programmatically.

The requirement should say:

> Every machine-consumed LLM output must use provider-native schema-constrained generation when available and must subsequently pass local JSON Schema or Pydantic validation before entering any durable queue or database.

The schema should enforce:

```python
model_config = ConfigDict(
    extra="forbid",
    strict=True,
)
```

It should also enforce:

* schema version;
* enumerated canonical metrics;
* confidence in ([0,1]);
* required evidence fields;
* valid transformation types;
* valid period types;
* known source concepts;
* unique candidate identifiers;
* explicit review status;
* nullable fields represented explicitly;
* no additional properties.

Schema validity alone is insufficient. Follow it with semantic validation:

```text
Does the concept exist in this filing?
Does its period type match the metric?
Is its unit compatible?
Is the proposed statement role valid?
Does the cited calculation parent exist?
Is the mapping allowed for this industry?
```

Failed schema validation should trigger a bounded retry. Repeated failure should produce a quarantined candidate rather than an improvised default.

All LLM-generated mappings should remain proposals. A deterministic mapping compiler should convert approved proposals into executable mapping rules.

## 4. Discontinued operations and comparability

The three proposed metrics belong in the core ontology:

```text
income_from_continuing_operations
income_from_discontinued_operations
net_income_total
```

I would extend the proposal beyond a Boolean `basis_change` field. Add a general comparability-event table:

```text
comparability_event
  entity_id
  event_id
  event_type
  effective_period
  first_filed_accession
  affected_metrics
  prior_basis_id
  new_basis_id
  source_evidence
  confidence
  review_status
```

Possible event types include:

```text
discontinued_operations_reclassification
reporting_currency_change
fiscal_calendar_change
major_accounting_standard_adoption
segment_reorganization
reverse_merger
fresh_start_accounting
major_acquisition
major_divestiture
```

Canonical observations should optionally carry:

```text
comparability_basis_id
comparability_status
```

This allows growth calculations to enforce:

[
\text{basis}*{t}=\text{basis}*{t-1}.
]

A simple flag identifies that something changed. A basis identifier establishes whether two particular observations are comparable.

This is especially important for revenue growth. After a discontinued-operation reclassification, a later filing may present an earlier period’s revenue on a continuing-operations basis. Both values can be correct:

[
\text{revenue}*{2024}^{\text{original basis}}
\neq
\text{revenue}*{2024}^{\text{recast continuing basis}}.
]

The point-in-time system must preserve both versions and their respective availability timestamps.

## 5. Amendment-scope classification

This should be a required stage before any `/A` filing enters revision analysis.

Add:

```text
amendment_scope
  accession
  amends_accession
  amendment_type
  has_primary_statement_delta
  affected_statements
  changed_fact_count
  changed_canonical_metric_count
  classification_method
  confidence
```

Recommended amendment types:

```text
nonfinancial_part_iii
cover_page_only
primary_financial_statements
financial_statement_notes
exhibits_only
xbrl_correction
mixed
unknown
```

The classifier should compare the amendment’s facts against the original accession. Filing form alone should never create a restatement event.

Revision-magnitude statistics should include only amendments or later filings that actually change canonical financial observations.

## 6. Offline taxonomy packages

This is mandatory for historical backfills.

The cache should include every taxonomy version referenced by the target filing universe, including deprecated historical versions. It should cover:

```text
us-gaap
dei
srt
country
currency
exch
stpr
document and entity schemas
role schemas
reference schemas
```

The cache should use offline XBRL Taxonomy Packages and URI catalogs. No parsing worker should attempt arbitrary network resolution during normal production processing.

Filer extension taxonomies belong to the accession’s immutable parser-input package rather than the shared taxonomy cache.

Each dataset build should pin:

```text
taxonomy_package_name
taxonomy_package_version
taxonomy_package_sha256
uri_catalog_sha256
```

This architecture also reduces pressure on SEC infrastructure. The SEC currently limits automated access to ten requests per second across the requesting system and requires a declared user agent.

## 7. Security-master construction

Parsing cover-page Inline XBRL is the right SEC-native spine, with two important qualifications.

First, cover-page tagging was phased in. Large accelerated U.S.-GAAP filers began with periods ending on or after June 15, 2019; accelerated filers followed in 2020; other filers followed in 2021. It cannot supply complete 2010–2019 security history.

Second, the data model must support multiple securities per CIK. SEC validation rules expressly contemplate multiple `Security12bTitle` observations represented through separate dimensional contexts.

Store cover-page observations as facts:

```text
cover_security_observation
  entity_id
  accession
  security_title
  trading_symbol
  exchange_name
  security_axis_member
  shares_outstanding
  measurement_date
  available_at
```

Then construct listing intervals through a separate inference process:

```text
listing_interval
  security_id
  ticker
  exchange
  valid_from
  valid_to
  evidence_accessions
  confidence
```

For the pre-tagging period, use a hierarchy such as:

1. filing cover-page text;
2. SEC filing headers;
3. historically archived SEC company-ticker files;
4. exchange symbol-directory snapshots;
5. registration statements;
6. merger, spin-off and delisting filings;
7. optional external ticker-change archives.

### Important naming correction

The public-data subproject should be called **SEC-to-market-security linking**, rather than CIK-to-CRSP/Compustat linking.

CRSP’s PERMNO is explicitly proprietary. A public project cannot independently manufacture authoritative PERMNO mappings.

CUSIP data also carries licensing constraints; CUSIP Global Services states that database storage and distribution may require a license. It should therefore be an optional licensed attribute rather than a foundational public identifier.

A suitable public identifier hierarchy is:

```text
internal_security_id
FIGI, where resolved
CIK
historical ticker
exchange
security title
share-class identity
```

FIGI identifiers are publicly available, and OpenFIGI provides a public mapping API, though the resulting mappings still require temporal validation rather than blind acceptance.

Licensed adapters can later map the internal security ID to:

```text
PERMNO
PERMCO
GVKEY
IID
licensed CUSIP
```

## 8. Release 1 scope

I agree with removing detailed footnote extraction from Release 1.

Release 1 should cover:

```text
cover page
balance sheet
income statement
statement of comprehensive income
cash-flow statement
statement of shareholders’ equity, where needed
```

Segment data, lease schedules, debt maturities, pension tables, tax footnotes, and textual disclosures should remain outside the initial Gold ontology.

The raw ingestion system may still retain the relevant filing documents so that later releases can add these features without reacquiring historical filings.

## 9. Parquet and DuckDB layout

The proposed storage guidance contains one technical statement I would change:

> “Metric is a column, let column pruning handle it.”

In a long-format canonical table, `metric_id` is a value within a column. Column pruning removes unused physical columns; it does not eliminate rows belonging to other metrics. Row-group statistics, sorting, partition pruning, and zone maps perform that work.

Use two physical representations.

### Canonical long table

```text
partition:
  available_year or filing_year
  optional metric_group

sort within files:
  metric_id
  entity_id
  available_at
  fiscal_period_end
```

This layout favors cross-sectional metric retrieval.

For company-history workloads, a second projection can sort:

```text
entity_id
metric_id
available_at
```

### Effective-interval PIT table

Instead of repeatedly calculating `arg_max(value, available_at)` over the complete history, materialize:

```text
metric_version_interval
  entity_id
  metric_id
  fiscal_period_id
  value
  valid_from
  valid_to
  accession
```

A point-in-time query then becomes:

```sql
WHERE valid_from <= :as_of
  AND (:as_of < valid_to OR valid_to IS NULL)
```

For common daily research workflows, a wide feature mart or periodic PIT snapshot table may be justified. Keep it derived from the canonical long-form source.

The ideal sort order depends on the dominant workload. U.S. equity quant research usually performs cross-sectional retrieval of a limited metric set across many entities, which favors `metric_id` earlier in the physical ordering.

## 10. Metamorphic tests

The invariants and test harness should precede Gold transformation development. The transformations themselves are needed before every test can pass.

Phase 1 should create:

* synthetic filing generators;
* timestamp boundary fixtures;
* amendment fixtures;
* restatement fixtures;
* fiscal-calendar fixtures;
* future-filing injection tests;
* deterministic dataset comparison tools.

Then each Gold transformation is merged only when the relevant invariants pass.

Add a particularly strong build-level test:

[
\operatorname{hash}\left(D_t(F_{\leq t})\right)
===============================================

\operatorname{hash}\left(D_t(F_{\leq T})\right),
\quad T>t.
]

The hash should be computed over logically normalized and deterministically sorted rows.

## 11. Fundamentals-to-returns interface

The plan should state clearly that a survivorship-free price, returns, and corporate-actions database is a separate product.

Define the contract now:

```text
market_observation
  security_id
  session_date
  open
  high
  low
  close
  volume
  raw_close
  split_factor
  dividend_amount
  total_return
  market_cap
  source_available_at
  source_version
  qc_status
```

The interface should specify:

* internal `security_id` as the join key;
* temporal listing validity;
* delisted-security retention;
* split and dividend treatment;
* delisting-return policy;
* observation availability;
* exchange calendar;
* corporate-action lineage.

This allows the fundamentals database to remain useful without claiming that the public EDGAR project also solves the full CRSP problem.

## 12. Core metric additions

Add:

```text
preferred_equity
preferred_dividends
redeemable_preferred_equity
temporary_equity
net_income_attributable_to_parent
net_income_attributable_to_noncontrolling_interests
```

These are needed to reconcile:

[
\text{net income attributable to common}
]

and to define book equity consistently.

A transparent book-equity family might contain:

```text
book_equity_reported
book_equity_common
book_equity_fama_french
tangible_common_equity
```

Each should have its own explicit formula and fallback rules.

## 13. Raw-storage policy

I agree with preserving the complete **parser input closure** rather than every exhibit attached to every accession.

The mandatory immutable set should include:

```text
filing index
primary filing document
XBRL instance or Inline XBRL documents
extension schema
presentation linkbase
calculation linkbase
definition linkbase
labels and references
filing header
every externally referenced document actually consumed by the parser
```

A manifest of all accession files can record names, sizes and SEC paths. Hashes require downloading the corresponding bytes, so “hash every full-package file while storing only selected files” remains an optional bandwidth-intensive audit mode.

A tiered policy is more practical:

```text
hot/warm:
  parser input closure

cold optional:
  complete submission text
  full accession package

reference only:
  irrelevant exhibits with SEC paths and metadata
```

## 14. Reproducibility

Replace byte-equivalence with logical equivalence.

Define a canonical content hash over:

* sorted primary keys;
* normalized numeric representations;
* normalized timestamps;
* explicit null representations;
* pinned transformation versions.

Parquet bytes can change because of compression libraries, metadata ordering, row-group construction, and writer versions even when the logical dataset is identical.

The release gate should require:

[
\operatorname{logical_hash}(D_1)
================================

\operatorname{logical_hash}(D_2).
]

## 15. Vintage quality and currency policy

Add `filing_vintage` and report every quality statistic by filing year and taxonomy version. Earlier XBRL vintages should receive a larger manually reviewed sample and stricter coverage reporting. I would let empirical error measurements determine whether particular metrics receive a later supported start date.

For currency:

* preserve every raw unit;
* retain reported currency in Gold;
* prohibit silent FX conversion;
* quarantine conflicting currencies for the same consolidated statement and period unless dimensions explain the difference;
* place translated values in the Research layer;
* require point-in-time FX rates and a versioned conversion policy.

The canonical table should distinguish:

```text
reported_value
reported_currency
converted_value
conversion_currency
fx_rate
fx_rate_date
fx_source_available_at
fx_policy_version
```

For Release 1, `converted_value` can remain unpopulated.

## Bottom line

The corrections should be incorporated. I would make four substantive changes to their exact wording:

1. Store information availability in Gold and derive trade eligibility in Research.
2. Use a process-isolated Arelle worker pool; require a microservice only when distribution warrants one.
3. Build an internal public security master with optional CRSP, Compustat, CUSIP and FIGI adapters.
4. Replace the suggested Parquet “column pruning” rationale with explicit row-group sorting, zone-map pruning, and effective-interval PIT tables.

With these changes, the plan becomes substantially closer to an implementable research-data system rather than a conceptual EDGAR extraction project.
