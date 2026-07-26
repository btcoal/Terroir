from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.bronze import BronzeStore  # noqa: E402
from us_fundamentals.build_manifest import (  # noqa: E402
    compare_manifests,
    create_release_manifest,
)

TAXONOMY_PIN = PROJECT_ROOT / "config" / "taxonomy_cache_manifest.json"

ROWS = [
    {
        "accession": "0000000001-24-000001",
        "metric_id": "assets_total",
        "value": 1.0,
        "available_at": datetime(2024, 2, 1, tzinfo=UTC),
    }
]


def _build(tmp: Path, rows: list[dict], compression: str) -> dict:
    bronze = BronzeStore(tmp / "bronze")
    bronze.add_object(
        "0000000001-24-000001",
        1234,
        "instance.xml",
        "instance",
        "https://www.sec.gov/x/instance.xml",
        b"<xbrl/>",
    )
    out = tmp / f"gold_{compression}.parquet"
    pq.write_table(pa.Table.from_pylist(rows), out, compression=compression)
    return create_release_manifest(
        dataset_version="ds-test-1",
        bronze=bronze,
        accessions=["0000000001-24-000001"],
        output_tables={"canonical_observation": (out, ["accession", "metric_id"])},
        component_versions={
            "parser": "arelle-2.x",
            "mapping": "0.0.0",
            "qc_rules": "0.0.0",
            "formulas": "0.0.0",
        },
        taxonomy_manifest_path=TAXONOMY_PIN,
        repo_root=PROJECT_ROOT,
    )


@unittest.skipIf(not TAXONOMY_PIN.exists(), "taxonomy cache manifest not pinned")
class ReleaseManifestTests(unittest.TestCase):
    def test_manifest_pins_every_required_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = _build(Path(tmp), ROWS, "snappy")
        for field in (
            "accessions",
            "taxonomy_packages",
            "component_versions",
            "code_commit",
            "built_at",
            "tables",
            "normalization_spec_version",
        ):
            self.assertIn(field, manifest, field)
        self.assertEqual(manifest["accessions"][0]["accession"], "0000000001-24-000001")
        self.assertTrue(manifest["accessions"][0]["objects"]["instance.xml"])
        self.assertGreater(len(manifest["taxonomy_packages"]), 50)
        for version in ("parser", "mapping", "qc_rules", "formulas"):
            self.assertIn(version, manifest["component_versions"])

    def test_identical_content_different_physical_layout_is_equivalent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            left = _build(Path(tmp) / "a", ROWS, "snappy")
            right = _build(Path(tmp) / "b", ROWS, "zstd")
        report = compare_manifests(left, right)
        self.assertTrue(report["content_identical"])
        self.assertTrue(report["tables"]["canonical_observation"]["equivalent"])

    def test_one_value_change_breaks_equivalence(self) -> None:
        changed = [dict(ROWS[0], value=2.0)]
        with tempfile.TemporaryDirectory() as tmp:
            left = _build(Path(tmp) / "a", ROWS, "snappy")
            right = _build(Path(tmp) / "b", changed, "snappy")
        report = compare_manifests(left, right)
        self.assertFalse(report["content_identical"])
        self.assertFalse(report["tables"]["canonical_observation"]["equivalent"])


if __name__ == "__main__":
    unittest.main()
