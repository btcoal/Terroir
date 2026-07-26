from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.eligibility import (  # noqa: E402
    FilingRecordError,
    ReleasePolicy,
    verify_fixture,
)


CONFIG_PATH = PROJECT_ROOT / "config" / "release_1_issuer_universe.json"
FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "release_1_eligibility_cases.json"
)


class ReleasePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = ReleasePolicy.from_file(CONFIG_PATH)
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_policy_is_frozen_at_version_one(self) -> None:
        self.assertEqual(self.policy.policy_id, "us_fundamentals_release_1")
        self.assertEqual(self.policy.policy_version, "1.0.0")

    def test_policy_permits_only_the_four_release_forms(self) -> None:
        self.assertEqual(
            self.policy.supported_forms,
            frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"}),
        )

    def test_fixture_decisions_match_the_policy(self) -> None:
        self.assertEqual(verify_fixture(self.policy, FIXTURE_PATH), [])

    def test_fixture_covers_every_inclusion_and_exclusion_category(self) -> None:
        categories = {case["category"] for case in self.fixture["cases"]}
        required = {
            "included_form_10_k",
            "included_form_10_q",
            "included_form_10_k_a",
            "included_form_10_q_a",
            "included_release_start_boundary",
            "excluded_form",
            "excluded_accounting_standard_ifrs",
            "excluded_registrant_type_foreign_private_issuer",
            "excluded_before_release_start",
        }
        required.update(
            f"excluded_issuer_type_{issuer_type}"
            for issuer_type in self.policy.unsupported_issuer_types
        )
        self.assertTrue(required.issubset(categories), required - categories)

    def test_ingestion_failure_does_not_change_eligibility(self) -> None:
        base = {
            "accession": "0000000001-24-999999",
            "form": "10-Q",
            "accounting_standard": "US-GAAP",
            "registrant_type": "domestic",
            "issuer_type": "operating_company",
            "sec_acceptance_datetime": "2024-07-01T12:00:00-04:00",
        }
        acquired = self.policy.evaluate({**base, "ingestion_status": "acquired"})
        failed = self.policy.evaluate(
            {**base, "ingestion_status": "terminal_failure"}
        )
        self.assertEqual(acquired.eligibility_status, "eligible")
        self.assertEqual(failed.eligibility_status, "eligible")
        self.assertNotEqual(acquired.ingestion_status, failed.ingestion_status)

    def test_unknown_metadata_is_not_silently_excluded(self) -> None:
        decision = self.policy.evaluate(
            {
                "accession": "0000000001-24-999998",
                "form": "10-K",
                "accounting_standard": "US-GAAP",
                "registrant_type": "unknown",
                "issuer_type": "unknown",
                "sec_acceptance_datetime": "2024-07-01T12:00:00-04:00",
            }
        )
        self.assertEqual(decision.eligibility_status, "indeterminate")
        self.assertEqual(
            decision.reason_codes,
            ("unknown_registrant_type", "unknown_issuer_type"),
        )

    def test_datetime_without_utc_offset_is_indeterminate(self) -> None:
        decision = self.policy.evaluate(
            {
                "accession": "0000000001-24-999997",
                "form": "10-K",
                "accounting_standard": "US-GAAP",
                "registrant_type": "domestic",
                "issuer_type": "operating_company",
                "sec_acceptance_datetime": "2024-07-01T12:00:00",
            }
        )
        self.assertEqual(decision.eligibility_status, "indeterminate")
        self.assertEqual(
            decision.reason_codes, ("invalid_sec_acceptance_datetime",)
        )

    def test_unknown_ingestion_status_is_rejected_as_bad_input(self) -> None:
        with self.assertRaises(FilingRecordError):
            self.policy.evaluate(
                {
                    "accession": "0000000001-24-999996",
                    "form": "10-K",
                    "accounting_standard": "US-GAAP",
                    "registrant_type": "domestic",
                    "issuer_type": "operating_company",
                    "sec_acceptance_datetime": "2024-07-01T12:00:00-04:00",
                    "ingestion_status": "lost",
                }
            )

    def test_metric_later_start_requires_evidence_and_versioning(self) -> None:
        self.assertTrue(self.policy.metric_later_start_allowed)
        self.assertTrue(self.policy.metric_later_start_requires_evidence)
        self.assertTrue(
            self.policy.metric_later_start_requires_version_increment
        )


if __name__ == "__main__":
    unittest.main()
