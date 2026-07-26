"""Logical dataset hashing and comparison (UF-014, ADR-0008).

Two datasets are logically equivalent when their normalized rows match:
row order, Parquet row-group layout, compression, numeric encoding,
timestamp representation, and null encoding must not affect the hash,
while any change to one value, timestamp, or lineage field must.

The normalization spec is versioned; changing it invalidates cross-version
hash comparison and requires a dataset version bump.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from us_fundamentals.errors import ContractViolationError

NORMALIZATION_SPEC_VERSION = "1.0.0"

_NULL = "␀"  # ␀ symbol: unambiguous null sentinel
_SEP = "␟"  # ␟ unit separator


def _normalize_value(value: Any) -> str:
    """Canonical string form for one cell."""
    if value is None:
        return _NULL
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if value == 0.0:
            return "0"  # collapses -0.0 and 0.0
        if math.isinf(value):
            return "Inf" if value > 0 else "-Inf"
        # repr() is the shortest round-trip form; strip trailing ".0" so
        # integral floats and ints written by different builds agree.
        text = repr(value)
        return text.removesuffix(".0")
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        normalized = value.normalize()
        text = format(normalized, "f")
        return text
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ContractViolationError(
                "naive datetime in a hashed table; store UTC-offset times"
            )
        return value.astimezone(tz=None).astimezone().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, str):
        return value
    raise ContractViolationError(f"unhashable cell type {type(value).__name__}")


def _normalize_datetime_utc(value: datetime) -> str:
    from datetime import UTC

    return value.astimezone(UTC).isoformat(timespec="microseconds")


def logical_hash(table: pa.Table, primary_key: list[str]) -> str:
    """Order-independent, layout-independent hash of a table's content."""
    missing = [k for k in primary_key if k not in table.column_names]
    if missing:
        raise ContractViolationError(f"primary key columns missing: {missing}")
    columns = sorted(table.column_names)
    rows = table.to_pylist()

    def canonical_row(row: dict[str, Any]) -> str:
        parts = []
        for column in columns:
            value = row[column]
            if isinstance(value, datetime) and value.tzinfo is not None:
                parts.append(_normalize_datetime_utc(value))
            else:
                parts.append(_normalize_value(value))
        return _SEP.join(parts)

    def key_of(row: dict[str, Any]) -> str:
        return _SEP.join(_normalize_value(row[k]) for k in primary_key)

    serialized = sorted((key_of(r), canonical_row(r)) for r in rows)
    digest = hashlib.sha256()
    digest.update(f"spec:{NORMALIZATION_SPEC_VERSION}".encode())
    digest.update(("cols:" + ",".join(columns)).encode())
    for key, row_text in serialized:
        digest.update(key.encode())
        digest.update(b"\x00")
        digest.update(row_text.encode())
        digest.update(b"\x01")
    return digest.hexdigest()


def logical_hash_parquet(path: Path, primary_key: list[str]) -> str:
    return logical_hash(pq.read_table(path), primary_key)


def diff_tables(
    left: pa.Table, right: pa.Table, primary_key: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Row-level differences between two logically comparable tables."""
    columns = sorted(set(left.column_names) | set(right.column_names))

    def index(table: pa.Table) -> dict[tuple, dict[str, Any]]:
        return {
            tuple(_normalize_value(row[k]) for k in primary_key): row
            for row in table.to_pylist()
        }

    left_rows, right_rows = index(left), index(right)
    only_left = [dict(left_rows[k]) for k in left_rows.keys() - right_rows.keys()]
    only_right = [dict(right_rows[k]) for k in right_rows.keys() - left_rows.keys()]
    changed = []
    for key in left_rows.keys() & right_rows.keys():
        deltas = {}
        for column in columns:
            l_val = _normalize_value(left_rows[key].get(column))
            r_val = _normalize_value(right_rows[key].get(column))
            if l_val != r_val:
                deltas[column] = {"left": l_val, "right": r_val}
        if deltas:
            changed.append({"key": list(key), "columns": deltas})
    return {
        "only_in_left": only_left,
        "only_in_right": only_right,
        "changed": changed,
    }


def diff_parquet(
    left_path: Path, right_path: Path, primary_key: list[str]
) -> dict[str, list[dict[str, Any]]]:
    return diff_tables(pq.read_table(left_path), pq.read_table(right_path), primary_key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    hash_cmd = sub.add_parser("hash")
    hash_cmd.add_argument("path", type=Path)
    hash_cmd.add_argument("--key", required=True, help="comma-separated PK columns")
    compare = sub.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.add_argument("--key", required=True)
    args = parser.parse_args(argv)
    key = args.key.split(",")

    if args.command == "hash":
        print(
            json.dumps(
                {
                    "path": str(args.path),
                    "normalization_spec": NORMALIZATION_SPEC_VERSION,
                    "logical_hash": logical_hash_parquet(args.path, key),
                }
            )
        )
        return 0

    differences = diff_parquet(args.left, args.right, key)
    equivalent = not any(differences.values())
    print(
        json.dumps(
            {"equivalent": equivalent, "differences": differences},
            indent=2,
            default=str,
        )
    )
    return 0 if equivalent else 1


if __name__ == "__main__":
    raise SystemExit(main())
