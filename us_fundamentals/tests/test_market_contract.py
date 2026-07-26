from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "market_observation.schema.json"


def _valid_row() -> dict:
    return {
        "security_id": "sec_000001",
        "session_date": "2012-06-14",
        "source": "future_market_source",
        "dataset_version": "md-0.0.1",
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "raw_close": 10.2,
        "share_volume": 125000,
        "cumulative_split_factor": 1.0,
        "cash_dividend": None,
        "corporate_action_ids": [],
        "total_return": 0.0132,
        "price_return": 0.0132,
        "delisting_return": None,
        "delisting_return_type": None,
        "market_cap": 51000000.0,
        "shares_outstanding_source": "cover_page",
        "source_available": "present",
        "qc_status": "pass",
    }


class MarketObservationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def test_schema_itself_is_valid(self) -> None:
        jsonschema.Draft202012Validator.check_schema(self.schema)

    def test_conforming_row_validates(self) -> None:
        self.validator.validate(_valid_row())

    def test_interface_specifies_every_required_field_group(self) -> None:
        fields = set(self.schema["properties"])
        for required in (
            "open",
            "high",
            "low",
            "close",
            "raw_close",
            "share_volume",
            "cumulative_split_factor",
            "cash_dividend",
            "total_return",
            "delisting_return",
            "market_cap",
            "source_available",
            "dataset_version",
            "qc_status",
            "security_id",
        ):
            self.assertIn(required, fields)

    def test_join_key_fields_are_required(self) -> None:
        for field in ("security_id", "session_date", "dataset_version"):
            row = _valid_row()
            del row[field]
            with self.assertRaises(jsonschema.ValidationError, msg=field):
                self.validator.validate(row)

    def test_split_factor_is_mandatory_so_adjustment_is_reversible(self) -> None:
        row = _valid_row()
        del row["cumulative_split_factor"]
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(row)

    def test_delisting_return_requires_a_type(self) -> None:
        row = _valid_row()
        row["delisting_return"] = -0.35
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(row)
        row["delisting_return_type"] = "exchange_final_print"
        self.validator.validate(row)

    def test_estimated_delisting_return_names_its_policy(self) -> None:
        row = _valid_row()
        row["delisting_return"] = -0.35
        row["delisting_return_type"] = "estimated_by_policy"
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(row)
        row["delisting_policy_version"] = "delist-est/1.0.0"
        self.validator.validate(row)

    def test_ticker_and_cusip_are_not_interface_fields(self) -> None:
        # The join key is security_id; ticker/CUSIP must not leak into the
        # market interface even as optional columns.
        for banned in ("ticker", "cusip", "permno", "permco", "gvkey", "iid"):
            self.assertNotIn(banned, self.schema["properties"])
        row = _valid_row()
        row["ticker"] = "ACME"
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(row)

    def test_absence_semantics_are_explicit(self) -> None:
        self.assertEqual(
            set(self.schema["properties"]["source_available"]["enum"]),
            {"present", "absent_in_source", "rejected_by_qc"},
        )


if __name__ == "__main__":
    unittest.main()
