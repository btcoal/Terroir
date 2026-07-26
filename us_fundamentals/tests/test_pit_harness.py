"""UF-015 PIT metamorphic harness.

CI runs this file as the dedicated PIT-leakage job; the required violation
count is zero, and any leakage is a hard failure.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.pit import (  # noqa: E402
    PITLeakageError,
    assert_pit_clean,
    check_pit_invariant,
    injections,
    restrict_corpus,
    snapshot,
)

CORPUS_PATH = PROJECT_ROOT / "tests" / "fixtures" / "pit_corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
CUTOFFS = [datetime.fromisoformat(c["at"]) for c in CORPUS["cutoffs"]]


def _value_at(table, entity: str, metric: str, period: str):
    for row in table.to_pylist():
        if (
            row["entity_id"] == entity
            and row["metric_id"] == metric
            and row["fiscal_period_id"] == period
        ):
            return row
    return None


class FixtureCoverageTests(unittest.TestCase):
    def test_required_fixture_categories_are_present(self) -> None:
        categories = {o["category"] for o in CORPUS["observations"]}
        categories.update(a["category"] for a in CORPUS["nonfinancial_amendments"])
        categories.update(p["category"] for p in CORPUS["incompatible_basis_pairs"])
        categories.update(listing.get("category", "") for listing in CORPUS["listings"])
        required = {
            "original_filing",
            "original_filing_ytd",
            "later_comparative_restatement",
            "financial_amendment",
            "nonfinancial_amendment",
            "future_filing",
            "mapping_version_change",
            "multiple_share_classes",
            "ticker_change_old",
            "ticker_change_new_then_delisted",
            "delisting",
            "fifty_two_fifty_three_week",
            "fiscal_year_change_transition_stub",
            "fiscal_year_change_new_calendar",
            "incompatible_bases",
        }
        self.assertTrue(required.issubset(categories), required - categories)

    def test_calendar_cutoffs_cover_required_cases(self) -> None:
        cutoff_categories = {c["category"] for c in CORPUS["cutoffs"]}
        for required in (
            "weekend",
            "holiday",
            "half_day_early_close",
            "dst_transition",
            "unscheduled_closure_pre_corpus",
        ):
            self.assertIn(required, cutoff_categories)


class PITInvariantTests(unittest.TestCase):
    def test_metamorphic_invariant_holds_at_every_cutoff(self) -> None:
        violations = check_pit_invariant(CORPUS, CUTOFFS)
        self.assertEqual(violations, [])  # required count: zero

    def test_assert_pit_clean_passes_for_reference_resolver(self) -> None:
        assert_pit_clean(CORPUS, CUTOFFS)

    def test_snapshot_versions_resolve_in_information_time(self) -> None:
        as_filed = snapshot(CORPUS, datetime.fromisoformat("2014-03-01T12:00:00-05:00"))
        row = _value_at(as_filed, "E1", "net_income_total", "E1-FY2013")
        self.assertEqual(row["value"], 100.0)  # original, pre-amendment

        after_amendment = snapshot(
            CORPUS, datetime.fromisoformat("2014-07-01T09:30:00-04:00")
        )
        row = _value_at(after_amendment, "E1", "net_income_total", "E1-FY2013")
        self.assertEqual(row["value"], 105.0)  # financial amendment wins

        after_restatement = snapshot(
            CORPUS, datetime.fromisoformat("2015-06-01T09:30:00-04:00")
        )
        row = _value_at(after_restatement, "E1", "net_income_total", "E1-FY2013")
        self.assertEqual(row["value"], 102.0)  # restated comparative wins

    def test_nonfinancial_amendment_never_displaces_a_value(self) -> None:
        before = snapshot(CORPUS, datetime.fromisoformat("2014-04-14T12:00:00-04:00"))
        after = snapshot(CORPUS, datetime.fromisoformat("2014-05-01T09:30:00-04:00"))
        for table in (before, after):
            row = _value_at(table, "E1", "net_income_total", "E1-FY2013")
            self.assertEqual(row["value"], 100.0)
            self.assertEqual(row["accession"], "E1-10K-FY2013")

    def test_mapping_release_is_pit_bounded(self) -> None:
        before_release = snapshot(
            CORPUS, datetime.fromisoformat("2014-12-31T12:00:00-05:00")
        )
        row = _value_at(before_release, "E1", "net_income_total", "E1-FY2013")
        self.assertEqual(row["mapping_version"], "map-1.0")
        after_release = snapshot(
            CORPUS, datetime.fromisoformat("2015-01-10T09:30:00-05:00")
        )
        row = _value_at(after_release, "E1", "net_income_total", "E1-FY2013")
        self.assertEqual(row["mapping_version"], "map-2.0")
        self.assertEqual(row["value"], 106.0)

    def test_historical_ticker_is_reconstructed_not_current(self) -> None:
        early = snapshot(CORPUS, datetime.fromisoformat("2014-03-01T12:00:00-05:00"))
        row = _value_at(early, "E3", "eps_diluted", "E3-FY2013")
        self.assertEqual(row["ticker"], "TCKA")
        later = snapshot(CORPUS, datetime.fromisoformat("2015-06-01T09:30:00-04:00"))
        row = _value_at(later, "E3", "eps_diluted", "E3-FY2013")
        self.assertEqual(row["ticker"], "TCKX")

    def test_delisted_security_remains_queryable(self) -> None:
        after_delisting = snapshot(
            CORPUS, datetime.fromisoformat("2015-07-15T09:30:00-04:00")
        )
        row = _value_at(after_delisting, "E3", "eps_diluted", "E3-FY2014")
        self.assertIsNotNone(row)
        self.assertIsNone(row["ticker"])  # no live listing, value still there

    def test_pre_corpus_snapshot_is_empty_not_an_error(self) -> None:
        table = snapshot(CORPUS, datetime.fromisoformat("2012-10-29T12:00:00-04:00"))
        self.assertEqual(table.num_rows, 0)


class LeakageDetectionTests(unittest.TestCase):
    """Injected leaks must make the harness fail — each category separately."""

    def test_every_injection_is_caught(self) -> None:
        for injection in injections():
            with self.subTest(injection=injection.name):
                with self.assertRaises(PITLeakageError):
                    assert_pit_clean(CORPUS, CUTOFFS, injection.snapshot_fn)

    def test_injected_amendment_changes_an_early_snapshot(self) -> None:
        clean = snapshot(CORPUS, datetime.fromisoformat("2014-03-01T12:00:00-05:00"))
        leaky_fn = next(
            i.snapshot_fn
            for i in injections()
            if i.name == "later_amendment_or_restatement"
        )
        leaky = leaky_fn(CORPUS, datetime.fromisoformat("2014-03-01T12:00:00-05:00"))
        clean_row = _value_at(clean, "E1", "net_income_total", "E1-FY2013")
        leaky_row = _value_at(leaky, "E1", "net_income_total", "E1-FY2013")
        self.assertEqual(clean_row["value"], 100.0)
        self.assertNotEqual(leaky_row["value"], 100.0)

    def test_restricting_the_corpus_is_lossless_at_the_horizon(self) -> None:
        horizon = max(CUTOFFS)
        restricted = restrict_corpus(CORPUS, horizon)
        self.assertEqual(len(restricted["observations"]), len(CORPUS["observations"]))


if __name__ == "__main__":
    unittest.main()
