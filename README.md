# Terroir

Terroir is a work-in-progress pipeline for building reproducible,
point-in-time fundamentals from SEC filings. Release 1 targets domestic
operating companies that report under U.S. GAAP and preserves each filing
version as it became available—without rewriting history with later
amendments, mappings, or identifier changes.

> [!IMPORTANT]
> Terroir is in the contract and foundation stage. The Release 1 scope,
> eligibility policy, and 128-metric data dictionary are implemented and
> tested; the end-to-end acquisition and transformation pipeline is still on
> the [roadmap](us_fundamentals/execution_tickets.md).

## Design principles

- **Point-in-time by construction.** Every accepted filing remains a distinct
  version tied to its SEC acceptance time.
- **Reproducible outputs.** Versioned policies, schemas, mappings, formulas,
  and build inputs make historical results explainable.
- **Complete provenance.** Published values must remain traceable to their
  accession, source fact, context, unit, dimensions, and transformation rules.
- **Explicit uncertainty.** Unsupported, invalid, and indeterminate records
  are classified rather than silently dropped.
- **No silent substitutions.** Reported values retain their source signs;
  reconstruction, imputation, incompatible-period arithmetic, and
  cross-currency arithmetic cannot masquerade as reported data.

## Release 1 scope

| Included | Not included |
| --- | --- |
| Forms `10-K`, `10-Q`, `10-K/A`, and `10-Q/A` | Detailed footnotes and unstructured-text extraction |
| Filings accepted on or after January 1, 2010 | Segment, lease, debt-maturity, pension, and tax schedules |
| Domestic U.S.-GAAP operating companies | Banks, insurers, REITs, utilities, investment companies, BDCs, shells, and asset-backed issuers |
| Cover page and primary financial statements | Market prices, returns, point-in-time FX translation, and imputation |
| Reported and explicitly derived canonical metrics | Silent restatement of earlier point-in-time snapshots |

Eligibility and ingestion are separate states. For example, an eligible 10-Q
that could not be downloaded remains **eligible** with an ingestion status of
`terminal_failure`; an acquired bank filing remains **excluded**.

See the [Release 1 charter](us_fundamentals/docs/release_1_charter.md) for the
complete boundary and rationale.

## What is implemented

- A frozen, executable
  [issuer-universe policy](us_fundamentals/config/release_1_issuer_universe.json)
  with deterministic `eligible`, `excluded`, and `indeterminate` decisions.
- A versioned
  [canonical data dictionary](us_fundamentals/docs/canonical_data_dictionary.md)
  containing 96 reported and 32 derived metric definitions.
- JSON Schemas plus stricter semantic validation for policy and dictionary
  contracts.
- Fixture coverage for every supported form, explicit issuer exclusion,
  filing-start boundary, indeterminate metadata, and ingestion failures.
- An execution backlog spanning acquisition, XBRL parsing, the security master,
  point-in-time resolution, quality control, and release operations.

## Quick start

The current validators use only the Python standard library and require
Python 3.10 or newer.

```bash
git clone https://github.com/btcoal/Terroir.git
cd Terroir/us_fundamentals

python3 -m unittest discover -s tests -v
```

Validate both frozen Release 1 contracts:

```bash
PYTHONPATH=src python3 -m us_fundamentals.eligibility validate-policy \
  --config config/release_1_issuer_universe.json

PYTHONPATH=src python3 -m us_fundamentals.data_dictionary validate \
  --dictionary config/canonical_data_dictionary.json
```

Inspect a canonical metric:

```bash
PYTHONPATH=src python3 -m us_fundamentals.data_dictionary show \
  --dictionary config/canonical_data_dictionary.json \
  --metric book_equity_fama_french
```

## Classify a filing

Create `filing.json` from normalized filing metadata:

```json
{
  "accession": "0000320193-24-000123",
  "form": "10-Q",
  "accounting_standard": "US-GAAP",
  "registrant_type": "domestic",
  "issuer_type": "operating_company",
  "sec_acceptance_datetime": "2024-08-02T18:01:42-04:00",
  "ingestion_status": "acquired"
}
```

Then evaluate it against the frozen policy:

```bash
PYTHONPATH=src python3 -m us_fundamentals.eligibility classify \
  --config config/release_1_issuer_universe.json \
  --input filing.json
```

The command returns the eligibility status, stable reason codes, policy
version, and the independently tracked ingestion status as JSON.

## Repository guide

```text
.
├── README.md
└── us_fundamentals/
    ├── config/       # Executable Release 1 contracts
    ├── docs/         # Human-readable contract documentation
    ├── schemas/      # JSON Schemas for machine-readable contracts
    ├── src/          # Standard-library validators and policy logic
    ├── tests/        # Unit tests and eligibility fixtures
    ├── tickets/      # Canonical implementation specifications
    └── execution_tickets.md
```

## Roadmap

Work is organized into seven milestones:

1. product contract;
2. correctness and storage foundations;
3. Bronze acquisition and Silver parsing;
4. temporal entity and security master;
5. Gold mapping, periodization, and point-in-time resolution;
6. quality control and research outputs;
7. historical release and production operation.

The [execution backlog](us_fundamentals/execution_tickets.md) is the source of
truth for dependencies, status, acceptance criteria, and release gates.

## Development

Start from a ticket in
[`us_fundamentals/tickets/`](us_fundamentals/tickets/) and keep code, tests,
schemas, migrations, documentation, and operational diagnostics together.
Before proposing a change, run:

```bash
cd us_fundamentals
python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m us_fundamentals.eligibility verify-fixture \
  --config config/release_1_issuer_universe.json \
  --fixture tests/fixtures/release_1_eligibility_cases.json
PYTHONPATH=src python3 -m us_fundamentals.data_dictionary validate \
  --dictionary config/canonical_data_dictionary.json
```
