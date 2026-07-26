from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.logical_hash import (  # noqa: E402
    diff_parquet,
    diff_tables,
    logical_hash,
    logical_hash_parquet,
)

KEY = ["accession", "metric_id"]


def sample_rows() -> list[dict]:
    eastern = timezone(timedelta(hours=-5))
    return [
        {
            "accession": "0000000001-24-000001",
            "metric_id": "assets_total",
            "value": 1000000.0,
            "available_at": datetime(2024, 2, 1, 21, 31, 30, tzinfo=UTC),
            "mapping_rule_id": "r-assets-1",
            "note": None,
        },
        {
            "accession": "0000000001-24-000001",
            "metric_id": "net_income_total",
            "value": 50000.5,
            "available_at": datetime(2024, 2, 1, 16, 31, 30, tzinfo=eastern),
            "mapping_rule_id": "r-ni-1",
            "note": "as filed",
        },
        {
            "accession": "0000000002-24-000009",
            "metric_id": "assets_total",
            "value": 0.0,
            "available_at": datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC),
            "mapping_rule_id": "r-assets-1",
            "note": None,
        },
    ]


def table(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows)


class LogicalHashTests(unittest.TestCase):
    def test_row_order_does_not_affect_hash(self) -> None:
        rows = sample_rows()
        self.assertEqual(
            logical_hash(table(rows), KEY),
            logical_hash(table(list(reversed(rows))), KEY),
        )

    def test_physical_parquet_layout_does_not_affect_hash(self) -> None:
        rows = sample_rows()
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left.parquet"
            right = Path(tmp) / "right.parquet"
            pq.write_table(table(rows), left, row_group_size=1, compression="snappy")
            pq.write_table(
                table(list(reversed(rows))),
                right,
                row_group_size=1000,
                compression="zstd",
            )
            self.assertEqual(
                logical_hash_parquet(left, KEY),
                logical_hash_parquet(right, KEY),
            )

    def test_equivalent_timestamps_in_different_zones_agree(self) -> None:
        rows_utc = sample_rows()
        eastern = timezone(timedelta(hours=-5))
        rows_local = sample_rows()
        rows_local[0]["available_at"] = datetime(
            2024, 2, 1, 16, 31, 30, tzinfo=eastern
        )  # same instant as 21:31:30Z
        self.assertEqual(
            logical_hash(table(rows_utc), KEY),
            logical_hash(table(rows_local), KEY),
        )

    def test_one_value_change_changes_hash(self) -> None:
        rows = sample_rows()
        changed = sample_rows()
        changed[0]["value"] += 0.01
        self.assertNotEqual(
            logical_hash(table(rows), KEY), logical_hash(table(changed), KEY)
        )

    def test_one_timestamp_change_changes_hash(self) -> None:
        rows = sample_rows()
        changed = sample_rows()
        changed[1]["available_at"] += timedelta(seconds=1)
        self.assertNotEqual(
            logical_hash(table(rows), KEY), logical_hash(table(changed), KEY)
        )

    def test_one_lineage_change_changes_hash(self) -> None:
        rows = sample_rows()
        changed = sample_rows()
        changed[2]["mapping_rule_id"] = "r-assets-2"
        self.assertNotEqual(
            logical_hash(table(rows), KEY), logical_hash(table(changed), KEY)
        )

    def test_null_and_zero_and_empty_are_distinct(self) -> None:
        base = [{"accession": "a", "metric_id": "m", "note": None}]
        zero = [{"accession": "a", "metric_id": "m", "note": "0"}]
        empty = [{"accession": "a", "metric_id": "m", "note": ""}]
        hashes = {
            logical_hash(table(base), KEY),
            logical_hash(table(zero), KEY),
            logical_hash(table(empty), KEY),
        }
        self.assertEqual(len(hashes), 3)


class DiffTests(unittest.TestCase):
    def test_full_and_incremental_builds_compare_row_level(self) -> None:
        full = sample_rows()
        incremental = sample_rows()
        incremental[0]["value"] = 999999.0  # changed
        incremental.pop(2)  # missing row
        incremental.append(  # extra row
            {
                "accession": "0000000003-24-000001",
                "metric_id": "assets_total",
                "value": 5.0,
                "available_at": datetime(2024, 4, 1, tzinfo=UTC),
                "mapping_rule_id": "r-assets-1",
                "note": None,
            }
        )
        diff = diff_tables(table(full), table(incremental), KEY)
        self.assertEqual(len(diff["only_in_left"]), 1)
        self.assertEqual(len(diff["only_in_right"]), 1)
        self.assertEqual(len(diff["changed"]), 1)
        self.assertIn("value", diff["changed"][0]["columns"])

    def test_equivalent_datasets_diff_empty_via_cli_shape(self) -> None:
        rows = sample_rows()
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "l.parquet"
            right = Path(tmp) / "r.parquet"
            pq.write_table(table(rows), left, compression="snappy")
            pq.write_table(table(list(reversed(rows))), right, compression="gzip")
            diff = diff_parquet(left, right, KEY)
        self.assertFalse(any(diff.values()))


if __name__ == "__main__":
    unittest.main()
