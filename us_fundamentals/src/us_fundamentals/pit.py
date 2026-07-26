"""Reference point-in-time snapshot resolver and metamorphic harness (UF-015).

`snapshot(corpus, as_of)` is the reference implementation of D_t: what was
knowable at t, resolved from filing versions, mapping releases, and listing
intervals, each bounded by its own information-availability time. The
metamorphic invariant is

    logical_hash(D_t(F_<=t)) == logical_hash(D_t(F_<=T))   for all T > t

— facts that arrive after t must be invisible to a snapshot at t. The
harness turns any violation into a counted, named PIT leakage failure; CI
requires the count to be zero. UF-049's production resolver must pass this
same harness over the same fixtures.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pyarrow as pa

from us_fundamentals.logical_hash import logical_hash


class PITLeakageError(AssertionError):
    """Raised when a snapshot at t is influenced by post-t information."""

    def __init__(self, violations: list[dict[str, Any]]) -> None:
        super().__init__(f"{len(violations)} PIT leakage violation(s)")
        self.violations = violations


SNAPSHOT_KEY = ["entity_id", "metric_id", "fiscal_period_id"]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _visible(row: Mapping[str, Any], as_of: datetime) -> bool:
    return _ts(row["information_available_at"]) <= as_of


def snapshot(corpus: Mapping[str, Any], as_of: datetime) -> pa.Table:
    """Reference D_t: resolve the corpus exactly as knowable at `as_of`."""
    observations = [o for o in corpus["observations"] if _visible(o, as_of)]

    # Latest mapping release available at as_of; observations carry the
    # mapping version that produced them, so later releases are invisible.
    releases = [r for r in corpus["mapping_releases"] if _visible(r, as_of)]
    if not releases:
        return pa.Table.from_pylist([])
    active_mapping = max(
        releases,
        key=lambda r: (_ts(r["information_available_at"]), r["mapping_version"]),
    )["mapping_version"]
    observations = [o for o in observations if o["mapping_version"] == active_mapping]

    # Filing-version resolution: for each economic period, the latest
    # *visible* version chain member wins; nonfinancial amendments carry no
    # observation rows so they can never displace a value.
    best: dict[tuple, dict[str, Any]] = {}
    for row in observations:
        key = (row["entity_id"], row["metric_id"], row["fiscal_period_id"])
        current = best.get(key)
        if current is None or (
            _ts(row["information_available_at"]),
            row["accession"],
        ) > (
            _ts(current["information_available_at"]),
            current["accession"],
        ):
            best[key] = row

    # Historical listing state: the interval covering as_of, never the
    # current row.
    tickers: dict[str, str | None] = {}
    for listing in corpus["listings"]:
        starts = _ts(listing["information_available_at"])
        ends = _ts(listing["superseded_at"]) if listing.get("superseded_at") else None
        if starts <= as_of and (ends is None or as_of < ends):
            tickers[listing["security_id"]] = listing["ticker"]

    rows = []
    for row in sorted(
        best.values(),
        key=lambda r: (r["entity_id"], r["metric_id"], r["fiscal_period_id"]),
    ):
        rows.append(
            {
                "entity_id": row["entity_id"],
                "metric_id": row["metric_id"],
                "fiscal_period_id": row["fiscal_period_id"],
                "value": row["value"],
                "accession": row["accession"],
                "mapping_version": row["mapping_version"],
                "comparability_basis_id": row.get("comparability_basis_id"),
                "ticker": tickers.get(row.get("security_id", ""), None),
            }
        )
    return pa.Table.from_pylist(rows) if rows else pa.Table.from_pylist([])


def restrict_corpus(corpus: Mapping[str, Any], horizon: datetime) -> dict[str, Any]:
    """F_<=T: drop everything that became knowable after the horizon."""
    return {
        "observations": [o for o in corpus["observations"] if _visible(o, horizon)],
        "mapping_releases": [
            r for r in corpus["mapping_releases"] if _visible(r, horizon)
        ],
        "listings": [
            dict(listing)
            for listing in corpus["listings"]
            if _visible(listing, horizon)
        ],
    }


SnapshotFn = Callable[[Mapping[str, Any], datetime], pa.Table]


def check_pit_invariant(
    corpus: Mapping[str, Any],
    cutoffs: list[datetime],
    snapshot_fn: SnapshotFn = snapshot,
    horizon: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return one violation record per cutoff where the invariant breaks."""
    if horizon is None:
        horizon = max(
            _ts(o["information_available_at"]) for o in corpus["observations"]
        )
    violations = []
    for cutoff in cutoffs:
        full = snapshot_fn(corpus, cutoff)
        restricted = snapshot_fn(restrict_corpus(corpus, cutoff), cutoff)
        full_hash = logical_hash(full, SNAPSHOT_KEY) if full.num_rows else "∅"
        restricted_hash = (
            logical_hash(restricted, SNAPSHOT_KEY) if restricted.num_rows else "∅"
        )
        if full_hash != restricted_hash:
            violations.append(
                {
                    "cutoff": cutoff.isoformat(),
                    "hash_with_future_facts": full_hash,
                    "hash_without_future_facts": restricted_hash,
                }
            )
    return violations


def assert_pit_clean(
    corpus: Mapping[str, Any],
    cutoffs: list[datetime],
    snapshot_fn: SnapshotFn = snapshot,
) -> None:
    violations = check_pit_invariant(corpus, cutoffs, snapshot_fn)
    if violations:
        raise PITLeakageError(violations)


@dataclass(frozen=True)
class LeakageInjection:
    """A deliberately broken snapshot function for harness self-tests."""

    name: str
    snapshot_fn: SnapshotFn


def injections() -> list[LeakageInjection]:
    """Corrupted resolvers, each leaking one kind of future information."""

    def later_filing_versions(corpus: Mapping[str, Any], as_of: datetime) -> pa.Table:
        # Amendments and restatements are applied regardless of when they
        # became knowable.
        cheat = {
            **corpus,
            "observations": [
                {**o, "information_available_at": as_of.isoformat()}
                if _ts(o["information_available_at"]) > as_of
                and o["mapping_version"] == "map-1.0"
                else o
                for o in corpus["observations"]
            ],
        }
        return snapshot(cheat, as_of)

    def latest_mapping_release(corpus: Mapping[str, Any], as_of: datetime) -> pa.Table:
        cheat = {
            **corpus,
            "mapping_releases": [
                {**r, "information_available_at": "2000-01-01T00:00:00+00:00"}
                for r in corpus["mapping_releases"]
            ],
        }
        return snapshot(cheat, as_of)

    def current_ticker(corpus: Mapping[str, Any], as_of: datetime) -> pa.Table:
        cheat = {
            **corpus,
            "listings": [
                {
                    **listing,
                    "information_available_at": "2000-01-01T00:00:00+00:00",
                    "superseded_at": None,
                }
                if listing.get("is_current")
                else {**listing, "superseded_at": "2000-01-02T00:00:00+00:00"}
                for listing in corpus["listings"]
            ],
        }
        return snapshot(cheat, as_of)

    return [
        LeakageInjection("later_amendment_or_restatement", later_filing_versions),
        LeakageInjection("later_mapping_release", latest_mapping_release),
        LeakageInjection("current_ticker_in_history", current_ticker),
    ]
