# Fundamentals-to-returns and identifier contracts

**Contract ID:** `us_fundamentals_market_interface`

**Contract version:** `1.0.0`

**Machine-readable interface:** `schemas/market_observation.schema.json`

Release 1 ships no prices, returns, or corporate actions. This contract fixes
the interface a future survivorship-free market dataset must satisfy so that
fundamentals built today join to it safely, without rework and without
implying the market dataset already exists.

## The `market_observation` interface

One row is one security, one session, one source, one dataset version. The
JSON Schema is normative; the summary:

| Field group | Fields |
| --- | --- |
| Identity | `security_id`, `session_date`, `source`, `dataset_version` |
| Prices | `open`, `high`, `low`, `close`, `raw_close` |
| Volume | `share_volume` |
| Corporate actions | `cumulative_split_factor`, `cash_dividend`, `corporate_action_ids` |
| Returns | `total_return`, `price_return`, `delisting_return`, `delisting_return_type` |
| Size | `market_cap`, `shares_outstanding_source` |
| Quality | `source_available`, `qc_status` |

Semantics that are contractual, not stylistic:

- `raw_close` is the exchange print, unadjusted. `close` may be
  split-adjusted only via `cumulative_split_factor`, so any adjustment is
  reversible; an adjusted price without its factor violates the contract.
- `total_return` includes dividends; `price_return` excludes them. Neither may
  be imputed from a missing price without `qc_status` saying so.
- `source_available` distinguishes "the source had no row" from "the source
  had a row we rejected"; absence of a `market_observation` row is never
  evidence the security did not trade.

## Join contract

- The join key is the internal **`security_id`**, never ticker, never CUSIP.
- A join is valid only where the fundamentals-side listing interval
  (UF-033's `valid_from`/`valid_to`) overlaps `session_date`. Joining outside
  listing validity is a contract violation even when a row exists.
- Fundamentals rows expose `security_id` plus `information_available_at`;
  the market side exposes `security_id` plus `session_date`. PIT joins align
  on the UF-003 execution policy, never on filing dates.

## Delisting contract

- Delisted securities are retained forever with their final listing interval
  closed, not deleted — the dataset is survivorship-free by construction.
- The final `market_observation` row for a delisted security carries
  `delisting_return` and `delisting_return_type`
  (`exchange_final_print`, `otc_continuation`, `estimated_by_policy`,
  `unknown`). An estimated delisting return must name the policy version that
  estimated it; silently substituting zero or a sector mean is forbidden.
- A missing delisting return is representable (`unknown`) and must never be
  silently dropped from return series; downstream code chooses its own
  treatment and records it.

## Corporate-action lineage

Every adjustment factor and dividend links to `corporate_action_ids` in a
corporate-action table (future dataset) carrying action type, ex-date, record
date, terms, and source. A factor with no action lineage is quarantined. Splits,
reverse splits, stock and cash dividends, spin-offs, and mergers must be
distinguishable; spin-off value assignment records its allocation policy.

## Calendar requirement

`session_date` must be a valid session in the same versioned exchange calendar
contract defined by UF-003. A market row on a non-session date is a QC
failure, not a timestamp to be reinterpreted.

## Public identifier hierarchy

In resolution order:

1. `security_id` — internal, permanent, opaque;
2. `entity_id` + CIK — the filing legal entity (one entity, many securities);
3. FIGI — optional, recorded with request/response version and observed time;
4. historical ticker + exchange — valid only within a listing interval;
5. security title and share class — evidence for inference, never join keys.

## Licensed identifiers are adapters only

PERMNO, PERMCO, GVKEY, IID, and licensed CUSIP mappings live behind optional
adapters in a separate namespace (UF-034). They may annotate, never define:
disabling every adapter must leave `security_id` assignments, listing
intervals, and all public outputs unchanged. Adapter output never overwrites
source evidence and is never a foundation for the public data model.

## Validation

`tests/test_market_contract.py` validates the schema itself, checks a
conforming example row, and rejects rows that break contractual semantics
(adjusted close without a split factor, delisting return without a type,
join fields missing).
