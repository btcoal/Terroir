# Information availability and execution-time policy

**Policy ID:** `us_fundamentals_availability`

**Policy version:** `1.0.0`

**Executable policy:** `config/availability_policy.json`

**Implementation:** `src/us_fundamentals/availability.py`

## The separation this policy enforces

Filing information time answers *when the market could know*. Execution
eligibility answers *when a specific strategy could trade on it*. The first is
a property of the filing and belongs to Gold. The second depends on a
strategy's calendar, latency, and session rules and belongs to the Research
layer. Gold fields must never encode a trading assumption, and Research
eligibility must never be used as a PIT information boundary.

## Gold availability fields

| Field | Meaning |
| --- | --- |
| `sec_acceptance_datetime` | EDGAR acceptance timestamp, with UTC offset |
| `information_available_at` | Earliest instant the filing is considered publicly knowable |
| `observed_first_seen_at` | When *our* pipeline first observed the filing; null for backfilled history |
| `availability_method` | How `information_available_at` was derived (enum below) |
| `availability_policy_version` | Version of this policy applied |
| `availability_confidence` | `exact`, `modeled`, or `assumed` |

`availability_method` values:

- `observed_dissemination`: we saw the filing arrive in near-real time;
  `information_available_at = observed_first_seen_at`.
- `acceptance_plus_buffer`: backfill rule;
  `information_available_at = sec_acceptance_datetime + dissemination_buffer`.
- `manual_evidence`: a documented source (e.g. press release timestamp)
  overrides the modeled time; requires review lineage.

The backfill dissemination buffer is configurable in the executable policy
(default 90 seconds) and the applied version is recorded on every row.
Changing the buffer requires a policy version increment; previously published
Gold rows retain the version they were computed under.

## EDGAR acceptance-hour semantics

EDGAR accepts filings 6:00–22:00 Eastern on business days. A filing accepted
after 17:30 Eastern receives the *next business day* as its filing date, but
its information is public on dissemination, minutes after acceptance. This
policy therefore keys availability to `sec_acceptance_datetime`, never to the
filing date. The 17:30 boundary matters only to filing-date reconciliation
against SEC indexes, not to `information_available_at`.

## Research execution contract

| Field | Meaning |
| --- | --- |
| `eligible_session` | First trading session whose selected reference time follows availability plus latency |
| `eligible_at_open` | Whether the information was available before that session's open |
| `eligible_at_close` | Whether it was available before that session's close |
| `execution_policy_version` | Version of the execution policy applied |

The default daily policy selects the first session whose **open** occurs after
`information_available_at + processing_latency`. Intraday policies must state
processing and execution latency explicitly; there is no implicit zero-latency
policy.

## Calendar contract

The execution calendar is versioned data, not code:

- times are stored with UTC offsets; session boundaries are defined in the
  exchange's local time zone (`America/New_York` for Release 1) and converted
  via the IANA tz database, so daylight-saving transitions are handled by the
  zone rules, not by fixed offsets;
- full holidays, half-days (early closes), and unscheduled closures
  (e.g. 2012-10-29/30 Hurricane Sandy) are explicit dated entries;
- a session record carries `session_date`, `open`, `close`, and `kind`
  (`full`, `half_day`); a missing date with no entry on a weekday is an error,
  never silently treated as open or closed;
- calendar edits produce a new calendar version; Research outputs record the
  version they used.

The checked-in Release 1 calendar fixture covers 2012 with U.S. holidays,
the July 3 half-day, the Sandy closure, and both DST transitions. The
production calendar is built at UF-055; this policy fixes its contract.

## Boundary semantics

For a session with open `O` and close `C` and availability instant `A`:

- `A < O`: eligible at that session's open and close.
- `O <= A < C`: not eligible at open; eligible at close only for policies
  that accept intra-session information, which the default daily policy does
  not — it defers to the next session's open.
- `A >= C` (including after 17:30 Eastern): eligible no earlier than the next
  session's open.
- `A` on a non-session day: eligible at the next session's open.

The fixture `tests/fixtures/availability_boundary_cases.json` encodes each of
these, including a filing accepted 16:29:59 Eastern (one second before close),
17:31 Eastern (after the filing-date cutoff), during the Sandy closure, on a
half-day after the 13:00 early close, and across both DST changes.

## Validation

```bash
PYTHONPATH=src python3 -m us_fundamentals.availability verify-fixture \
  --config config/availability_policy.json \
  --calendar tests/fixtures/calendar_2012.json \
  --fixture tests/fixtures/availability_boundary_cases.json
```
