from __future__ import annotations

import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.data_dictionary import (  # noqa: E402
    CanonicalDataDictionary,
    DictionaryValidationError,
    main,
    validate_dictionary_payload,
)


DICTIONARY_PATH = PROJECT_ROOT / "config" / "canonical_data_dictionary.json"


class CanonicalDataDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
        cls.dictionary = CanonicalDataDictionary.from_file(DICTIONARY_PATH)

    def test_dictionary_is_frozen_and_release_sized(self) -> None:
        self.assertEqual(self.dictionary.schema_version, 1)
        self.assertEqual(self.dictionary.dictionary_version, "1.0.0")
        self.assertEqual(self.dictionary.release, "1")
        self.assertGreaterEqual(len(self.dictionary.metrics), 100)
        self.assertLessEqual(len(self.dictionary.metrics), 150)

    def test_every_metric_has_complete_contract_fields(self) -> None:
        for metric in self.dictionary.metrics:
            with self.subTest(metric=metric.metric_id):
                self.assertTrue(metric.name)
                self.assertTrue(metric.definition)
                self.assertTrue(metric.industry_applicability)
                self.assertTrue(metric.fallback_rules)
                self.assertTrue(metric.version_added)

    def test_required_income_and_equity_metrics_exist(self) -> None:
        required = {
            "income_from_continuing_operations",
            "income_from_discontinued_operations",
            "net_income_total",
            "net_income_attributable_to_parent",
            "net_income_attributable_to_noncontrolling_interests",
            "preferred_equity",
            "preferred_dividends",
            "redeemable_preferred_equity",
            "temporary_equity",
        }
        self.assertTrue(required.issubset(self.dictionary.by_id))

    def test_book_equity_variants_are_separate_and_formula_backed(self) -> None:
        metric_ids = {
            "book_equity_reported",
            "book_equity_common",
            "book_equity_fama_french",
            "tangible_common_equity",
        }
        metrics = [self.dictionary.get(metric_id) for metric_id in metric_ids]
        self.assertEqual({metric.metric_id for metric in metrics}, metric_ids)
        self.assertEqual(
            len({metric.definition for metric in metrics}), len(metric_ids)
        )
        for metric in metrics:
            self.assertEqual(metric.metric_kind, "derived")
            self.assertIsNotNone(metric.formula)
            self.assertTrue(metric.fallback_rules)

    def test_ebitda_definitions_do_not_silently_fallback_to_each_other(self) -> None:
        reported = self.dictionary.get("ebitda_reported")
        reconstructed = self.dictionary.get("ebitda_reconstructed")
        adjusted = self.dictionary.get("ebitda_before_stock_comp")
        self.assertEqual(reported.metric_kind, "reported")
        self.assertEqual(reported.formula["method"], "direct")
        self.assertEqual(reconstructed.formula["method"], "calculation")
        self.assertIn(
            "stock_based_compensation", adjusted.formula["required_inputs"]
        )
        self.assertEqual(
            len(
                {
                    reported.formula["expression"],
                    reconstructed.formula["expression"],
                    adjusted.formula["expression"],
                }
            ),
            3,
        )

    def test_all_formula_inputs_exist(self) -> None:
        known = set(self.dictionary.by_id)
        for metric in self.dictionary.metrics:
            if metric.formula is None:
                continue
            inputs = set(metric.formula["required_inputs"])
            inputs.update(metric.formula["optional_inputs"])
            self.assertTrue(inputs.issubset(known), metric.metric_id)

    def test_duplicate_metric_ids_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["metrics"].append(copy.deepcopy(payload["metrics"][0]))
        errors = validate_dictionary_payload(payload)
        self.assertTrue(
            any("duplicate metric IDs" in error for error in errors), errors
        )

    def test_invalid_enums_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["metrics"][0]["period_type"] = "quarterly"
        errors = validate_dictionary_payload(payload)
        self.assertTrue(
            any(".period_type must be one of" in error for error in errors),
            errors,
        )

    def test_incomplete_definitions_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        del payload["metrics"][0]["definition"]
        errors = validate_dictionary_payload(payload)
        self.assertTrue(
            any("missing required fields: definition" in error for error in errors),
            errors,
        )

    def test_unknown_formula_inputs_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        metric = next(
            item
            for item in payload["metrics"]
            if item["metric_id"] == "net_debt"
        )
        metric["formula"]["required_inputs"].append("missing_metric")
        errors = validate_dictionary_payload(payload)
        self.assertTrue(
            any("references unknown metric missing_metric" in error for error in errors),
            errors,
        )

    def test_derived_metrics_cannot_claim_direct_formulas(self) -> None:
        payload = copy.deepcopy(self.payload)
        metric = next(
            item
            for item in payload["metrics"]
            if item["metric_id"] == "net_debt"
        )
        metric["formula"]["method"] = "direct"
        errors = validate_dictionary_payload(payload)
        self.assertTrue(
            any("cannot be direct when derived" in error for error in errors),
            errors,
        )

    def test_formula_dependency_cycles_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        first = next(
            item
            for item in payload["metrics"]
            if item["metric_id"] == "total_debt"
        )
        second = next(
            item
            for item in payload["metrics"]
            if item["metric_id"] == "net_debt"
        )
        first["formula"]["required_inputs"].append("net_debt")
        second["formula"]["required_inputs"].append("total_debt")
        errors = validate_dictionary_payload(payload)
        self.assertTrue(
            any("formula dependency cycle" in error for error in errors), errors
        )

    def test_loader_raises_with_all_validation_errors(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["metrics"][0]["unit"] = "dollars"
        with self.assertRaises(DictionaryValidationError) as context:
            CanonicalDataDictionary.from_mapping(payload)
        self.assertTrue(any(".unit must be one of" in item for item in context.exception.errors))

    def test_validation_command_reports_metric_count_and_hash(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                ["validate", "--dictionary", str(DICTIONARY_PATH)]
            )
        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["metric_count"], len(self.dictionary.metrics))
        self.assertEqual(result["logical_hash"], self.dictionary.logical_hash)


if __name__ == "__main__":
    unittest.main()
