# Release 1 charter: point-in-time U.S. fundamentals

**Charter ID:** `us_fundamentals_release_1`

**Policy version:** `1.0.0`

**Status:** Frozen

**Executable policy:** `config/release_1_issuer_universe.json`

## Product outcome

Release 1 produces point-in-time fundamentals for domestic operating companies
that report under U.S. GAAP. Every accepted filing remains a distinct version;
later filings, amendments, mappings, and identifier changes must not rewrite an
earlier point-in-time snapshot.

The release includes facts sourced from:

- the cover page;
- the balance sheet;
- the income statement;
- the statement of comprehensive income;
- the cash-flow statement;
- the statement of shareholders' equity where needed.

Release 1 does not include detailed footnote or unstructured-text extraction,
segment or geographic schedules, lease or debt-maturity schedules, pension
tables, tax footnotes, market prices or returns, point-in-time FX translation,
or imputation.

## Filing eligibility

A filing is eligible when all of the following are true:

1. `sec_acceptance_datetime` is on or after
   `2010-01-01T00:00:00-05:00`. The boundary is inclusive and the input must
   carry a UTC offset.
2. `form` is `10-K`, `10-Q`, `10-K/A`, or `10-Q/A`.
3. `accounting_standard` is `US-GAAP`.
4. `registrant_type` is `domestic`.
5. `issuer_type` is `operating_company`.

The start is based on filing vintage, not fiscal-period end. An eligible filing
may present earlier comparative periods, which remain traceable to that
filing's later information-availability time.

Amendments are eligible inputs but are not presumed to revise financial
statements. Amendment-scope classification is a later pipeline responsibility.

## Explicit issuer exclusions

The following normalized issuer types are recognized but unsupported:

- banks;
- insurers;
- real-estate investment trusts;
- utilities;
- investment companies;
- business development companies;
- shell companies;
- asset-backed issuers;
- other specialized registrants without a Release 1 accounting schema.

Foreign private issuers and non-U.S.-GAAP filers are also unsupported.
Unsupported records stay in the accession inventory with their exclusion
reason. An unrecognized or missing classification is `indeterminate`, never a
silent exclusion.

`registrant_type` and `issuer_type` are normalized classification inputs.
Their source evidence and classification version must be retained by the
inventory builder. A later ticket may improve classification evidence without
changing this eligibility contract; adding a supported class requires a new
policy version.

## Eligibility and ingestion are separate

Eligibility answers whether a filing belongs to the Release 1 denominator.
Ingestion status answers what happened while acquiring it. These states must
not be collapsed.

For example, an eligible 10-Q with `terminal_failure` remains eligible and
failed; an acquired bank 10-K remains acquired and excluded. Supported
ingestion states are:

```text
not_recorded
not_attempted
acquired
retry_pending
terminal_failure
unavailable_upstream
```

The policy returns one of:

- `eligible`: all required eligibility attributes satisfy the policy;
- `excluded`: at least one known attribute definitively excludes the filing;
- `indeterminate`: no definitive exclusion exists, but required metadata is
  missing, invalid, or unrecognized.

## Early-vintage metric policy

The Release 1 filing boundary does not imply that every metric is supported
uniformly from 2010. A metric may receive a later supported start only when:

1. measured vintage-specific quality supports the change;
2. the evidence and affected metric are documented;
3. the executable policy and metric dictionary receive new versions;
4. earlier raw and Silver observations remain retained and queryable.

This is a support and publication rule, not permission to erase early filings.

## Using the executable policy

The implementation uses only the Python standard library:

```bash
PYTHONPATH=src python3 -m us_fundamentals.eligibility validate-policy \
  --config config/release_1_issuer_universe.json

PYTHONPATH=src python3 -m us_fundamentals.eligibility verify-fixture \
  --config config/release_1_issuer_universe.json \
  --fixture tests/fixtures/release_1_eligibility_cases.json

python3 -m unittest discover -s tests
```

To classify one normalized filing, place its fields in a JSON object and run:

```bash
PYTHONPATH=src python3 -m us_fundamentals.eligibility classify \
  --config config/release_1_issuer_universe.json \
  --input path/to/filing.json
```

The checked-in fixture includes each supported form, every explicit exclusion,
the filing-start boundary, indeterminate metadata, and ingestion failures.
