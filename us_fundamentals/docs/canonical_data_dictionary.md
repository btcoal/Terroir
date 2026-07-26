# Release 1 canonical data dictionary

The machine-readable Release 1 accounting contract is
[`config/canonical_data_dictionary.json`](../config/canonical_data_dictionary.json).
It is validated by
[`schemas/canonical_data_dictionary.schema.json`](../schemas/canonical_data_dictionary.schema.json)
and the stricter semantic checks in
[`src/us_fundamentals/data_dictionary.py`](../src/us_fundamentals/data_dictionary.py).

Version `1.0.0` contains 128 metrics: 96 reported definitions and 32 derived
definitions.

## Contract

Each metric explicitly defines:

- a stable lower-snake-case `metric_id` and human name;
- whether it is reported or derived;
- its economic definition and source statement;
- instant or duration period type;
- unit and natural accounting polarity;
- allowed dimensional scope;
- industry applicability and exclusions;
- launch materiality tier;
- a versioned formula where calculation is permitted;
- ordered fallback rules;
- the dictionary version in which it first appeared.

`polarity` describes the natural accounting orientation used by mapping and QC
rules. It does not authorize changing a reported source value. The dictionary's
`reported_value_preserved` convention requires raw reported values and source
signs to remain recoverable.

Release 1 applies only to `all_release_1`, meaning the ordinary domestic
U.S.-GAAP operating-company universe frozen by UF-001. Specialist issuer
schemas require a later charter and dictionary version.

## Definition families

Metrics that are often collapsed by vendors remain distinct:

- total net income, parent income, noncontrolling-interest income, common
  income, continuing-operations income, and discontinued-operations income;
- total, preferred, redeemable, temporary, common, and noncontrolling equity;
- reported, common, Fama-French, and tangible-common book equity;
- directly reported EBITDA, reconstructed EBITDA, and EBITDA before
  stock-based compensation.

A directly reported value never silently falls back to a reconstructed value.
Reconstruction and adjustment produce their own metric IDs with separate
formula lineage.

## Formula rules

Every derived metric has a semantic formula version, expression, required and
optional canonical inputs, and compatibility constraints. The validator rejects
unknown inputs, self-reference, and dependency cycles.

Inputs to one calculation must share the entity, currency, dimensional scope,
fiscal-period basis, comparability basis, and point-in-time eligibility required
by the formula. `AVG`, `LAG`, and `TTM` in expressions are declarative operators;
their executable implementations belong to later Gold and Research tickets.

Fallback rules are ordered policy statements. They may choose among compatible
reported inputs or decline to publish a value. They never authorize imputation,
cross-currency arithmetic, incompatible-period arithmetic, or a source-value
rewrite.

## Materiality tiers

- `core`: launch-gate metrics receiving the strictest mapping and audit sample.
- `standard`: Release 1 metrics required for complete statements or common
  research formulas.
- `supplemental`: useful but less consistently presented Release 1 metrics.

## Commands

The validator uses only the Python standard library:

```bash
PYTHONPATH=src python3 -m us_fundamentals.data_dictionary validate \
  --dictionary config/canonical_data_dictionary.json

PYTHONPATH=src python3 -m us_fundamentals.data_dictionary show \
  --dictionary config/canonical_data_dictionary.json \
  --metric book_equity_fama_french

python3 -m unittest discover -s tests
```

Validation reports the dictionary version, metric count, and a stable hash of
the canonical JSON content. Duplicate metric IDs, unknown fields, invalid
enums, incomplete definitions, broken formula references, and dependency
cycles are hard failures.
