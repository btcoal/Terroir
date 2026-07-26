from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.availability import (  # noqa: E402
    AvailabilityPolicy,
    AvailabilityPolicyError,
    AvailabilityRecordError,
    TradingCalendar,
    verify_fixture,
)

CONFIG_PATH = PROJECT_ROOT / "config" / "availability_policy.json"
CALENDAR_PATH = PROJECT_ROOT / "tests" / "fixtures" / "calendar_2012.json"
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "availability_boundary_cases.json"


class AvailabilityPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = AvailabilityPolicy.from_file(CONFIG_PATH)
        cls.calendar = TradingCalendar.from_file(CALENDAR_PATH)
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_boundary_fixture_passes(self) -> None:
        self.assertEqual(verify_fixture(self.policy, self.calendar, FIXTURE_PATH), [])

    def test_fixture_covers_required_boundary_categories(self) -> None:
        categories = {case["category"] for case in self.fixture["cases"]}
        required = {
            "before_open",
            "during_session",
            "just_before_close",
            "after_close",
            "after_1730_eastern",
            "non_session_day",
            "half_day",
            "dst",
            "availability_method",
        }
        self.assertTrue(required.issubset(categories), required - categories)

    def test_backfill_records_policy_version_and_buffer(self) -> None:
        gold = self.policy.compute_availability(
            {"sec_acceptance_datetime": "2012-06-14T12:00:00-04:00"}
        )
        self.assertEqual(gold["availability_policy_version"], "1.0.0")
        available = datetime.fromisoformat(gold["information_available_at"])
        accepted = datetime.fromisoformat(gold["sec_acceptance_datetime"])
        self.assertEqual(available - accepted, timedelta(seconds=90))

    def test_naive_acceptance_datetime_is_rejected(self) -> None:
        with self.assertRaises(AvailabilityRecordError):
            self.policy.compute_availability(
                {"sec_acceptance_datetime": "2012-06-14T12:00:00"}
            )

    def test_calendar_rejects_missing_weekday_entries(self) -> None:
        payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        payload["sessions"] = [
            s for s in payload["sessions"] if s["session_date"] != "2012-06-14"
        ]
        broken = PROJECT_ROOT / "tests" / "fixtures" / "_broken_calendar.json"
        broken.write_text(json.dumps(payload), encoding="utf-8")
        try:
            with self.assertRaises(AvailabilityPolicyError):
                TradingCalendar.from_file(broken)
        finally:
            broken.unlink()

    def test_eligibility_outside_coverage_is_an_error_not_a_guess(self) -> None:
        with self.assertRaises(AvailabilityRecordError):
            self.policy.compute_eligibility(
                datetime.fromisoformat("2013-01-02T10:00:00-05:00"), self.calendar
            )

    def test_half_day_close_is_1300_eastern(self) -> None:
        session = self.calendar.sessions[
            datetime.fromisoformat("2012-07-03T00:00:00-04:00").date()
        ]
        self.assertEqual(session.kind, "half_day")
        self.assertEqual(session.close_at.isoformat(), "2012-07-03T13:00:00-04:00")

    def test_execution_policy_never_moves_information_time(self) -> None:
        record = {"sec_acceptance_datetime": "2012-06-14T15:59:59-04:00"}
        gold = self.policy.compute_availability(record)
        research = self.policy.compute_eligibility(
            datetime.fromisoformat(gold["information_available_at"]), self.calendar
        )
        self.assertEqual(research["eligible_session"], "2012-06-15")
        # Gold availability is unchanged by the deferral to the next session.
        self.assertEqual(gold["information_available_at"], "2012-06-14T16:01:29-04:00")


if __name__ == "__main__":
    unittest.main()
