Below is a project specification that can be handed to an advanced coding agent and used to govern implementation.

# Implementation Plan: Open, Point-in-Time Company Fundamentals Database for U.S. Equity Research

## 1. Objective

Build a research-grade company fundamentals database from publicly available SEC EDGAR filings. The database should support cross-sectional equity modeling, factor construction, portfolio backtesting, forecasting, event studies, and fundamental screening.

The intended result is a Compustat-like research dataset for U.S. public equities from approximately 2010 onward. The system should prioritize:

* point-in-time correctness;
* survivorship-free historical coverage;
* stable definitions across companies and time;
* transparent transformations;
* complete source provenance;
* reproducible historical snapshots;
* explicit data-quality indicators;
* compatibility with market-price and returns datasets.

The database does not need to reproduce Compustat field-for-field. It should reproduce the economically relevant accounting information while making every normalization rule inspectable.

The primary output should answer questions such as:

```sql
SELECT *
FROM fundamentals_pit
WHERE security_id = :security
  AND available_at <= :research_date
  AND metric IN ('revenue', 'net_income', 'book_equity');
```

A researcher should also be able to obtain the latest restated historical series or the exact information available at an earlier date.

## 2. Definition of a Successful First Release

The first release should cover domestic operating companies reporting under U.S. GAAP and filing Forms 10-K and 10-Q. It should initially exclude investment companies, shell companies, asset-backed issuers, and other specialized registrants. Banks, insurers, REITs, and utilities should either receive separate accounting schemas or enter in later releases.

The initial period should begin in 2010 or 2011, when XBRL coverage became sufficiently broad. The SEC’s bulk Financial Statement Data Sets begin in 2009 and provide quarterly flattened data extracted from structured filings. The SEC reprocessed these datasets in December 2024 so that primary-statement observations are selected using the Commission’s rendering data, including a new segment field. These datasets are useful as an independent reconciliation source, although the SEC explicitly warns that they can contain filer or extraction errors.

The first production ontology should contain approximately 100–150 canonical metrics. Fifty highly important metrics should receive especially stringent manual validation.

The initial output should contain four distinct views:

1. `raw_facts`: Every parsed XBRL fact with no economic reinterpretation.
2. `fundamentals_as_filed`: Canonical values exactly as represented by each filing.
3. `fundamentals_latest`: The latest known restated value for every company-period-metric.
4. `fundamentals_pit`: The value available to a researcher at a specified timestamp.

A fifth layer, `derived_fundamentals`, should contain explicitly defined calculations such as book equity, net debt, trailing-twelve-month revenue, operating profitability, accruals, and asset growth.

## 3. Governing Principle for the LLM

The LLM should act as an engineering agent, accounting-research assistant, and anomaly triage system. Deterministic software should remain the authority for data values, period arithmetic, accounting identities, and production database writes.

The LLM may:

* design schemas and migrations;
* write and test parsers;
* inspect XBRL taxonomies and filing structures;
* propose mappings from custom concepts to canonical metrics;
* generate review packets for ambiguous observations;
* identify likely period, sign, dimensional, and taxonomy errors;
* write unit, integration, regression, and property-based tests;
* summarize discrepancies between sources;
* propose new validation rules;
* maintain technical and accounting documentation.

The LLM should never:

* silently change a reported value;
* infer a missing value without labeling it as derived or imputed;
* promote a concept mapping without passing deterministic tests;
* resolve an accounting discrepancy by deleting the observation;
* overwrite a prior filing version;
* use data filed after the requested historical research timestamp;
* treat ticker symbols as permanent company identifiers;
* make production schema changes without a migration and version increment.

Every LLM-produced mapping decision should be expressed in a structured record:

```json
{
  "source_concept": "abc:AdjustedOperatingIncome",
  "canonical_metric": "operating_income",
  "transformation": "identity",
  "scope": "consolidated",
  "confidence": 0.97,
  "evidence": {
    "definition": "...",
    "statement_role": "income_statement",
    "presentation_parent": "...",
    "calculation_relationships": ["..."],
    "historical_concepts": ["..."],
    "filing_excerpt": "..."
  },
  "alternatives": ["adjusted_operating_income_non_gaap"],
  "review_required": true
}
```

Free-form LLM conclusions should never directly modify normalized data.

## 4. Data Sources

### 4.1 SEC submissions and XBRL APIs

Use the SEC Submissions API for filer histories and metadata, including names, ticker symbols, exchanges, forms, accession numbers, and filing dates. Use the Company Facts API as a convenient source for standard taxonomy facts and as an independent check against the raw parser.

The SEC APIs require no authentication, update throughout the day, and provide nightly bulk archives for both submissions and company facts. Bulk archives should be used for historical initialization, followed by incremental ingestion for newly disseminated filings.

### 4.2 Raw filing archives

Download the complete filing package for each target accession:

* primary Inline XBRL document;
* XBRL instance document where separately supplied;
* taxonomy extension schema;
* calculation linkbase;
* presentation linkbase;
* definition linkbase;
* labels and references;
* filing index and header;
* complete submission text file.

The raw filing package is the ultimate provenance record. Every downloaded byte should be stored immutably with a cryptographic hash.

### 4.3 SEC bulk Financial Statement and Notes datasets

Use the SEC’s Financial Statement Data Sets and Financial Statement and Notes Data Sets as reconciliation sources. They provide flattened observations that can expose parser omissions and make broad coverage checks easier. The notes datasets can later support segment, debt-maturity, lease, pension, and other footnote-derived variables.

### 4.4 XBRL validation software

Use Arelle as the reference XBRL processor. It supports XBRL 2.1, Dimensions, Inline XBRL, SEC EDGAR Filer Manual validation, calculation validation, and other relevant specifications. Pin the exact Arelle version used for each database release.

Run the current effective XBRL US Data Quality Committee rules as an additional validation layer. These publicly available rules detect problems such as invalid dimensions, reversed calculations, inconsistent ratios, impossible value relationships, and inappropriate taxonomy usage. The release version and rule effective dates must be stored with every validation result.

### 4.5 Access policy

Prefer bulk downloads and cache all retrieved files. Identify the application with a declared user agent and administrative contact. Throttle all SEC traffic below the Commission’s current limit of ten requests per second across the complete system.

## 5. Storage Architecture

Use an immutable, layered architecture.

| Layer    | Purpose                                                                   |
| -------- | ------------------------------------------------------------------------- |
| Bronze   | Original SEC files, API payloads, checksums and download manifests        |
| Silver   | Parsed XBRL facts, contexts, units, dimensions and taxonomy relationships |
| Gold     | Canonical accounting observations with standardized metrics and periods   |
| Research | Derived variables, point-in-time panels and model-ready snapshots         |

A practical implementation can use:

* S3-compatible object storage for raw filing packages;
* Parquet with Apache Iceberg or Delta-style versioning for large analytical tables;
* PostgreSQL for metadata, mapping rules, review decisions and operational state;
* DuckDB or Polars for local research access;
* Dagster, Prefect or an equivalent orchestrator for dependency-aware jobs;
* Arelle for standards-compliant parsing and validation.

Every dataset release should have a manifest containing:

* source accession set;
* raw-file checksums;
* parser version;
* taxonomy versions;
* mapping-rule version;
* validation-rule version;
* transformation-code commit;
* build timestamp;
* output-table checksums.

A complete rebuild from the same manifest should produce byte-equivalent or logically equivalent outputs.

## 6. Core Data Model

### 6.1 Entity and security tables

Use separate identifiers for legal entities, securities, and listings.

```text
entity
  entity_id
  cik
  legal_name
  incorporation
  fiscal_year_end
  entity_type
  valid_from
  valid_to

security
  security_id
  entity_id
  share_class
  security_type
  cusip
  figi
  valid_from
  valid_to

listing
  listing_id
  security_id
  ticker
  exchange
  valid_from
  valid_to
```

CIK should be the primary SEC filer identifier. The SEC states that CIKs are unique to filers and are not recycled. A CIK can still represent multiple securities, and securities can change ticker or exchange.

Seed current mappings from the SEC company-ticker file and cover-page XBRL tags. Build historical listing intervals from filing cover pages, filing headers, exchange symbol directories, merger disclosures, spin-off filings, and prospectively archived daily exchange snapshots. Preserve inactive and delisted securities.

A survivorship-free security master is one of the hardest parts of the project. It should be treated as a distinct data product with its own QC process.

### 6.2 Filing table

```text
filing
  accession
  entity_id
  form
  amendment_flag
  report_period
  filing_date
  acceptance_datetime
  availability_datetime
  fiscal_year
  fiscal_period
  taxonomy_version
  source_url_key
  raw_manifest_hash
```

Use the EDGAR acceptance timestamp as the base information timestamp. The SEC reports that filings are often publicly available within one to three minutes of the EDGAR timestamp. A conservative research policy can define:

```text
availability_time = acceptance_time + 5 minutes
```

The five-minute buffer is a project policy and should remain configurable. For daily strategies, a filing accepted after the research cutoff should become usable on the following trading session.

### 6.3 Raw fact table

```text
raw_fact
  accession
  fact_id
  concept_qname
  taxonomy_namespace
  context_id
  unit_id
  raw_value
  numeric_value
  decimals
  precision
  nil_flag
  period_type
  period_start
  period_end
  instant_date
  dimensions_json
  dimensions_hash
  statement_role
  presentation_order
  source_document
  source_location
```

Preserve all dimensional facts. Consolidated, segment, geographic, product, debt-class, share-class, and other observations should coexist in the raw layer.

### 6.4 Canonical observation table

```text
canonical_observation
  entity_id
  security_id
  metric_id
  fiscal_period_id
  period_start
  period_end
  period_type
  value
  currency
  unit
  scope
  derivation_type
  accession
  filed_at
  available_at
  source_concept
  source_context
  mapping_rule_id
  mapping_confidence
  qc_status
  dataset_version
```

`derivation_type` should distinguish:

* directly reported;
* aggregated from reported components;
* derived quarterly value;
* trailing-twelve-month value;
* standardized research metric;
* manually overridden;
* imputed.

Initial production releases should avoid imputation.

## 7. Canonical Accounting Ontology

Begin with a compact ontology that is valuable for equity research.

### Balance sheet

Include cash, restricted cash, short-term investments, receivables, inventory, current assets, PP&E gross and net, operating lease assets, goodwill, acquired intangibles, total assets, accounts payable, accrued liabilities, current debt, long-term debt, lease liabilities, current liabilities, total liabilities, preferred equity, common equity, retained earnings, accumulated other comprehensive income, treasury stock and noncontrolling interests.

### Income statement

Include revenue, cost of revenue, gross profit, research and development, selling and marketing, general and administrative expense, depreciation and amortization, operating income, interest expense, interest income, nonoperating income, pretax income, income tax expense, continuing-operations income, net income, net income attributable to common shareholders, basic EPS, diluted EPS, and weighted-average shares.

### Cash-flow statement

Include operating cash flow, capital expenditures, acquisitions, asset disposals, investing cash flow, debt issuance, debt repayment, common-stock issuance, repurchases, dividends, financing cash flow, depreciation and amortization, stock-based compensation, deferred taxes and working-capital adjustments.

### Other research variables

Include shares outstanding, fiscal-year-end date, employee count when available, common dividends per share, segment revenue, geographic revenue, backlog, and selected industry-specific metrics.

Maintain separate definitions where common vendor fields conceal meaningful ambiguity. For example:

```text
ebitda_reported
ebitda_reconstructed
ebitda_before_stock_comp
```

Each definition should have an explicit formula and source hierarchy.

## 8. Concept-Mapping System

### 8.1 Standard concepts

Maintain deterministic mappings for standard U.S. GAAP concepts. A mapping rule should specify:

* canonical metric;
* allowed taxonomy versions;
* permitted forms;
* required period type;
* permitted units;
* required or prohibited dimensions;
* acceptable statement roles;
* sign treatment;
* priority relative to alternative concepts;
* industry applicability.

### 8.2 Custom concepts

SEC filers can create company-specific XBRL tags. The SEC has repeatedly observed that custom tags reduce cross-company comparability when companies use them where standard tags would suffice.

The LLM should map custom concepts using an evidence hierarchy:

1. taxonomy definition and label;
2. calculation parents and children;
3. presentation-tree location;
4. statement role;
5. period type and XBRL datatype;
6. unit;
7. balance attribute;
8. dimensional structure;
9. neighboring line items;
10. prior filings by the same company;
11. similar concepts used by peer companies;
12. visible filing text and table headings.

Concept-name similarity alone is insufficient.

Custom mappings should have three operational states:

* `candidate`: generated by the LLM;
* `approved`: reviewed or validated against a high-precision rule;
* `rejected`: explicitly prohibited.

Automated promotion should occur only after the estimated precision of the mapping process exceeds the project’s acceptance threshold on a manually labeled sample.

### 8.3 Mapping-rule versioning

A mapping correction should generate a new database version. Historical outputs from earlier mapping versions must remain reproducible.

Never edit an already released mapping rule in place.

## 9. Periodization and Fiscal-Calendar Logic

Period handling should be implemented as a dedicated subsystem.

### 9.1 Instant and duration facts

Classify each fact as:

* instant;
* fiscal quarter;
* year-to-date;
* fiscal year;
* transition period;
* nonstandard duration.

Do not rely exclusively on the filing’s `fp` field. Validate the classification from start date, end date, fiscal-year end, form, statement role, and surrounding facts.

### 9.2 Derived quarterly values

Companies often report cash-flow and some income-statement values on a year-to-date basis. Derive standalone quarters only when the fiscal bases are compatible:

```text
Q_2 = H_1 - Q_1,
Q_3 = 9M - H_1,
Q_4 = FY - 9M.
```

The source observations must share:

* the same accounting scope;
* the same currency;
* compatible dimensions;
* the same fiscal year;
* compatible restatement status;
* logically contiguous dates.

Store the reported cumulative facts and derived quarterly facts separately.

### 9.3 Irregular calendars

Explicitly handle:

* 52- and 53-week fiscal years;
* fiscal-year-end changes;
* transition reports;
* mergers and reverse mergers;
* IPO stub periods;
* companies with non-calendar fiscal years;
* filings containing comparative periods under different accounting bases.

SEC calendar-frame endpoints should serve as exploratory data rather than the principal periodization method because the SEC notes that frames align facts approximately to calendar periods even when company fiscal calendars differ.

## 10. Restatements, Amendments and Point-in-Time Views

Never overwrite a previously filed observation.

For every entity-period-metric, preserve a version chain:

```text
original filing
subsequent comparative presentation
10-K/A or 10-Q/A amendment
later restated comparative value
latest known value
```

Provide three query semantics:

```text
V_as_filed(a)
```

returns the value in accession (a).

```text
V_latest(p)
```

returns the most recently filed value for fiscal period (p).

```text
V_PIT(p,t)
```

returns the latest value for fiscal period (p) whose availability timestamp is no later than (t).

The point-in-time resolver should be a pure deterministic function with extensive regression tests.

A mapping-rule change is different from a filing restatement. Store both the economic version and the normalization-version lineage.

## 11. Derived Research Variables

Derived values should be calculated only from canonical observations that passed the necessary QC gates.

Initial derived variables should include:

* trailing-twelve-month revenue and earnings;
* book equity;
* tangible book equity;
* total debt and net debt;
* gross profitability;
* operating profitability;
* return on assets;
* return on equity;
* operating and net margins;
* accruals;
* asset growth;
* investment growth;
* sales growth;
* earnings growth;
* research-and-development intensity;
* capital-expenditure intensity;
* stock-based-compensation intensity;
* equity issuance and repurchase measures;
* leverage;
* cash-flow-to-assets;
* dividend payout;
* diluted-share growth.

Every derived metric should have:

```text
metric definition
formula version
required inputs
fallback hierarchy
industry exclusions
unit
expected sign or domain
PIT lag policy
```

The research layer should never combine filing-period data with market prices unless both were available at the requested research timestamp.

## 12. Validation and Quality-Control Framework

QC should operate at several independent levels. A single successful check should never be treated as proof of correctness.

### 12.1 Acquisition QC

Reconcile the set of downloaded accessions against:

* SEC daily and quarterly indexes;
* Submissions API histories;
* bulk submissions archives;
* expected 10-K and 10-Q filing sequences.

For every accession:

* verify HTTP success and file size;
* calculate SHA-256 hashes;
* verify that required filing documents are present;
* detect truncated or malformed downloads;
* verify that the accession belongs to the expected CIK;
* detect duplicate ingestion;
* retain a permanent download log.

A full historical build and an incremental build over the same accession set should produce the same raw-file manifest.

### 12.2 Parser QC

Run each filing through Arelle and retain all validation messages.

Test:

* XBRL 2.1 conformance;
* Inline XBRL conformance;
* taxonomy loading;
* context validity;
* dimensional validity;
* unit validity;
* duplicate fact consistency;
* calculation relationships;
* SEC EDGAR Filer Manual rules;
* effective DQC rules.

Compare the internal parser’s output against Arelle for a golden corpus. Fact counts, concept names, periods, dimensions, units and values should agree exactly.

### 12.3 Exact raw-source reconciliation

For standard concepts, compare parsed observations with:

* SEC Company Facts;
* SEC Financial Statement Data Sets;
* SEC Financial Statement and Notes Data Sets.

Where possible, join on accession, concept, unit, period and dimensional scope.

Differences should be classified as:

* source excludes a custom concept;
* source selects only primary-statement facts;
* dimensional fact excluded;
* duplicate-context selection difference;
* taxonomy-version difference;
* SEC extraction difference;
* internal parser defect;
* unresolved.

Unresolved mismatches should generate a quarantined observation and review ticket.

### 12.4 Accounting identity checks

Validate both taxonomy-defined calculations and project-defined accounting identities.

Examples include:

[
\text{Assets}
\approx
\text{Liabilities}+\text{Equity},
]

with alternative formulations for noncontrolling interest, redeemable noncontrolling interest, temporary equity and other presentation structures.

Additional checks include:

[
\text{Gross profit}
\approx
\text{Revenue}-\text{Cost of revenue},
]

[
\text{Ending cash}
\approx
\text{Beginning cash}+\text{Net change in cash},
]

[
\text{Operating income}
\approx
\text{Gross profit}-\text{Operating expenses},
]

when all relevant components are available and definitions are compatible.

Use rounding-aware tolerances based on XBRL `decimals`. For a numeric fact with reported decimals (d_i), define an approximate rounding uncertainty:

[
u_i = \frac{1}{2}10^{-d_i}.
]

For a calculation

[
P = \sum_i w_i C_i,
]

accept the relationship when:

[
\left|P-\sum_i w_i C_i\right|
\le
u_P+\sum_i |w_i|u_i+\epsilon,
]

where (\epsilon) handles floating-point representation. Facts reported with infinite precision should receive zero XBRL rounding uncertainty.

Accounting identities should produce explanatory residuals. The system should never force an identity to balance by altering a source value.

### 12.5 Cross-statement checks

Compare economically equivalent observations across statements:

* income-statement net income versus cash-flow-statement net income;
* cash-flow ending cash versus balance-sheet cash and restricted cash;
* depreciation expense versus depreciation add-back;
* common shares outstanding versus cover-page shares;
* debt totals versus debt-note components;
* segment revenue totals versus consolidated revenue;
* accumulated depreciation versus gross and net PP&E;
* EPS, earnings and weighted-average shares.

Differences should allow for valid definitional distinctions and should record the reason when known.

### 12.6 Temporal checks

For each company and metric:

* detect overlapping fiscal periods;
* detect missing fiscal quarters;
* verify that fiscal periods progress in order;
* reconcile derived quarters to annual totals;
* identify sudden fiscal-year-end changes;
* detect implausible duplicate values across periods;
* detect sign reversals associated with mapping changes;
* detect unit changes;
* compare original and restated values;
* flag very large revisions;
* flag concept substitutions that create discontinuities.

Use robust within-company change scores and cross-sectional industry-year distributions to prioritize review. Outlier status should create a warning rather than automatically modify the data.

### 12.7 Point-in-time leakage checks

Create hard automated tests proving that:

* an observation cannot appear before its filing availability timestamp;
* an amendment cannot alter an earlier point-in-time query;
* a later comparative restatement cannot enter an earlier snapshot;
* a mapping version released later cannot silently alter an archived research snapshot;
* a filing accepted after the daily cutoff cannot affect that day’s features;
* a delisted company remains in historical universes;
* current ticker mappings do not rewrite historical tickers.

A powerful metamorphic test is:

$$
D(t; F_{\le t}) = D(t; F_{\le T}),
\qquad T>t
$$

where (D(t;\cdot)) is the point-in-time dataset for date (t). Adding filings after (t) must leave the result unchanged.

The required number of point-in-time leakage violations is zero.

### 12.8 Human-audited golden corpus

Construct a manually audited benchmark containing at least several hundred filings, stratified across:

* 10-K and 10-Q;
* amendments;
* large and small companies;
* every major industry;
* standard and custom concepts;
* calendar and non-calendar fiscal years;
* 52- and 53-week years;
* IPOs and transition periods;
* mergers and spin-offs;
* multiple share classes;
* companies with high custom-tag rates;
* banks, insurers and REITs once supported.

For the fifty core metrics, manually compare canonical values to the visible primary statements and footnotes.

Each audited observation should record:

* expected canonical metric;
* expected value;
* expected period;
* source location;
* source concept;
* expected dimensions;
* acceptable alternative representations;
* auditor notes.

This corpus should be version controlled and used for every release.

### 12.9 Mapping precision and confidence calibration

Measure concept-mapping performance as a classification problem.

Report:

* precision by canonical metric;
* recall by canonical metric;
* coverage;
* precision for standard concepts;
* precision for custom concepts;
* precision by industry;
* precision by filer size;
* precision by taxonomy year;
* calibration of LLM confidence scores.

Mappings that affect highly material variables such as revenue, assets, net income, book equity, shares, operating cash flow or capital expenditures should require stricter thresholds.

A recommended launch gate is:

* at least 99.5% estimated precision for the fifty core metrics;
* at least 98% coverage for ordinary nonfinancial operating companies;
* at least 99% precision for the next tier of metrics;
* manual review for unrecognized custom concepts;
* no silent fallback to a semantically weaker concept.

### 12.10 Research-level validation

Validate the database through complete research workflows.

Construct representative signals such as:

* book-to-market;
* gross profitability;
* operating profitability;
* asset growth;
* accruals;
* investment;
* earnings yield;
* sales growth;
* share issuance;
* leverage.

Test whether:

* coverage remains stable through time;
* missingness is related to company size or industry;
* signal distributions remain economically plausible;
* portfolios can be reconstructed from archived PIT snapshots;
* factor results are stable across rebuilds;
* results do not collapse when low-confidence mappings are excluded;
* results remain stable when observations with QC warnings are excluded.

If temporary access to Compustat or another normalized source is available, compare a stratified sample rather than blindly optimizing agreement. Classify each disagreement as:

* different accounting definition;
* different period selection;
* restatement timing;
* vendor adjustment;
* security-entity mapping;
* internal error;
* vendor error;
* unresolved.

The objective is explained disagreement, rather than mechanical equality with a commercial product.

## 13. QC Status and Quarantine Policy

Every canonical observation should receive one of these statuses:

| Status            | Meaning                                      |
| ----------------- | -------------------------------------------- |
| Pass              | All required checks passed                   |
| Pass with warning | Usable with a documented noncritical anomaly |
| Review            | Ambiguous mapping or unresolved discrepancy  |
| Quarantined       | Excluded from standard research outputs      |
| Rejected          | Known incorrect or unsupported observation   |

Hard-failure examples include:

* malformed or unparseable filing;
* unresolved duplicate canonical observations;
* incompatible units;
* impossible PIT timestamp;
* accession or CIK mismatch;
* mapping outside its permitted taxonomy or industry;
* unexplained source-value alteration;
* failure of an explicitly required identity;
* missing provenance.

The raw fact should remain available even when the canonical observation is quarantined.

## 14. LLM Review Workflow

For each ambiguous case, the LLM should create a review packet containing:

1. company, accession, form and fiscal period;
2. visible filing excerpt;
3. XBRL concept definition and labels;
4. period and dimensions;
5. statement and presentation-tree location;
6. calculation relationships;
7. prior-year concepts used by the company;
8. comparable peer-company concepts;
9. proposed canonical mapping;
10. alternative mappings;
11. expected downstream effect;
12. confidence score;
13. failed QC rules.

A reviewer can approve, reject or modify the proposed rule. The decision should become a versioned test fixture so that the same ambiguity does not recur silently.

## 15. Implementation Sequence

### Phase 0: Project charter and specification

Define:

* target issuer universe;
* supported forms;
* starting date;
* accounting standards;
* canonical metrics;
* PIT cutoff policy;
* exclusion rules;
* release acceptance criteria.

Produce a written data dictionary before implementing metric mappings.

### Phase 1: Repository and reproducibility framework

Create:

* typed configuration;
* database migrations;
* object-storage conventions;
* deterministic build manifests;
* structured logging;
* retry and checkpoint logic;
* CI pipeline;
* unit and integration test framework;
* dataset-versioning convention.

### Phase 2: Historical ingestion

Load:

* bulk submissions;
* bulk company facts;
* quarterly Financial Statement Data Sets;
* all target raw filing packages.

Reconcile expected and observed accession counts before proceeding.

### Phase 3: XBRL parsing

Integrate Arelle, extract all facts and taxonomy relationships, and populate silver-layer tables.

Complete the raw-parser golden-corpus tests before writing canonical mappings.

### Phase 4: Entity and security master

Create temporal company, security and listing records. Separate current identifiers from historical mappings and preserve inactive entities.

### Phase 5: Canonical ontology and mappings

Implement the first fifty core metrics. Validate them deeply before expanding to the next hundred.

Begin with direct standard-tag mappings. Add custom-tag handling after standard mappings and periodization are stable.

### Phase 6: Fiscal-period and point-in-time engine

Implement instant and duration classification, standalone-quarter derivation, amendments, restatements, latest-known views and PIT queries.

Build adversarial leakage tests before allowing backtesting.

### Phase 7: Derived research metrics

Implement versioned formulas using only approved canonical inputs. Keep alternative accounting definitions separate.

### Phase 8: Full QC system

Add acquisition, parser, accounting, cross-source, temporal, cross-sectional and PIT validation. Build quarantine queues and review packets.

### Phase 9: Benchmark study

Run the system against the golden corpus, visible filings, SEC bulk datasets and an optional commercial benchmark.

Publish precision, coverage, disagreement and missingness reports.

### Phase 10: Production operation

Implement:

* nightly incremental ingestion;
* periodic full rebuilds;
* taxonomy-update procedures;
* mapping-change reviews;
* data drift dashboards;
* failed-filing alerts;
* release manifests;
* archived PIT snapshots.

## 16. Release Gates

A research release should require all of the following:

1. At least 99.95% of expected target accessions were acquired or explicitly accounted for.
2. Every raw file has a checksum and source manifest.
3. The internal parser agrees exactly with the reference parser on the golden corpus.
4. Every canonical value has complete accession-level provenance.
5. No unresolved duplicate primary keys exist.
6. No PIT leakage test fails.
7. Core-metric mapping precision exceeds the agreed threshold.
8. Accounting-identity failures are either resolved or quarantined.
9. Cross-source mismatches are classified.
10. Incremental and full rebuilds produce equivalent datasets.
11. Research outputs are reproducible from a pinned release manifest.
12. Low-confidence and quarantined data can be excluded through a simple query flag.
13. A human-readable release report documents coverage, known gaps and methodology changes.

## 17. Recommended Initial Deliverable

The first useful release should concentrate on ordinary industrial and technology companies and contain approximately fifty variables:

```text
revenue
cost_of_revenue
gross_profit
research_and_development
selling_general_administrative
operating_income
interest_expense
pretax_income
income_tax
net_income
net_income_common
basic_eps
diluted_eps
basic_weighted_average_shares
diluted_weighted_average_shares

cash_and_equivalents
short_term_investments
accounts_receivable
inventory
current_assets
property_plant_equipment_net
goodwill
intangible_assets
total_assets
accounts_payable
current_liabilities
short_term_debt
long_term_debt
total_liabilities
common_equity
retained_earnings
noncontrolling_interest

operating_cash_flow
capital_expenditures
acquisitions
investing_cash_flow
debt_issuance
debt_repayment
share_issuance
share_repurchases
dividends_paid
financing_cash_flow
depreciation_and_amortization
stock_based_compensation

shares_outstanding
fiscal_year_end
filing_timestamp
availability_timestamp
```

This subset is large enough to support most classical equity factors and financial-statement forecasting while remaining small enough to audit thoroughly.

## 18. Central Design Judgment

The project’s primary engineering challenge is the preservation of accounting meaning across companies, taxonomies, fiscal periods and filing versions.

XML parsing should be treated as infrastructure. The durable intellectual property will be:

* the canonical accounting ontology;
* concept-selection rules;
* fiscal-period engine;
* point-in-time version model;
* security master;
* validation corpus;
* mapping decision history;
* QC and quarantine framework.

The database will become trustworthy when every displayed number can answer four questions:

1. Where in the filing did this value come from?
2. Why was this concept mapped to this metric?
3. When did the information become available?
4. Which tests did the value pass or fail?

A useful next step would be converting this into an executable repository specification with epics, table DDL, Python interfaces, and acceptance-test stubs.

