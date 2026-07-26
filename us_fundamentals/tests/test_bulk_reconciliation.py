from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.bulk_reconciliation import (  # noqa: E402
    catalog_source,
    coverage_report,
    index_companyfacts,
    ingest_fsds,
)

SUB_TXT = (
    "adsh\tcik\tname\tform\tperiod\tfy\tfp\tfiled\n"
    "0000001234-16-000001\t1234\tACME CORP\t10-K\t20151231\t2015\tFY\t20160220\n"
    "0000009999-16-000077\t9999\tOTHER CO\t10-Q\t20160331\t2016\tQ1\t20160504\n"
)
NUM_TXT = (
    "adsh\ttag\tversion\tddate\tqtrs\tuom\tvalue\tfootnote\n"
    "0000001234-16-000001\tAssets\tus-gaap/2015\t20151231\t0\tUSD\t1000000\t\n"
    "0000001234-16-000001\tNetIncomeLoss\tus-gaap/2015\t20151231\t4\tUSD\t50000\t\n"
)
NOTE_TXT = "adsh\tnote\n0000001234-16-000001\tsome long note text\n"

COMPANYFACTS = {
    "cik": 1234,
    "entityName": "ACME CORP",
    "facts": {
        "us-gaap": {
            "Assets": {
                "units": {
                    "USD": [
                        {
                            "end": "2015-12-31",
                            "val": 1000000,
                            "accn": "0000001234-16-000001",
                            "form": "10-K",
                        },
                        {
                            "end": "2014-12-31",
                            "val": 900000,
                            "accn": "0000001234-15-000001",
                            "form": "10-K",
                        },
                    ]
                }
            }
        },
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {
                    "shares": [
                        {
                            "end": "2016-01-31",
                            "val": 1000,
                            "accn": "0000001234-16-000001",
                            "form": "10-K",
                        }
                    ]
                }
            }
        },
    },
}


def make_fsds_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sub.txt", SUB_TXT)
        archive.writestr("num.txt", NUM_TXT)
        archive.writestr("note.txt", NOTE_TXT)


def make_companyfacts_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("CIK0000001234.json", json.dumps(COMPANYFACTS))


class CatalogTests(unittest.TestCase):
    def test_catalog_is_append_only_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "2016q1.zip"
            make_fsds_zip(zip_path)
            catalog = Path(tmp) / "catalog.json"
            first = catalog_source(zip_path, catalog)
            second = catalog_source(zip_path, catalog)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(len(json.loads(catalog.read_text())), 1)
            # A new upstream vintage of the same file appends, not replaces.
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("sub.txt", SUB_TXT + "extra\t\t\t\t\t\t\t\n")
            catalog_source(zip_path, catalog)
            entries = json.loads(catalog.read_text())
            self.assertEqual(len(entries), 2)
            self.assertNotEqual(entries[0]["sha256"], entries[1]["sha256"])
            for entry in entries:
                self.assertIn("retrieved_at", entry)
                self.assertIn("sha256", entry)


class FsdsIngestTests(unittest.TestCase):
    def test_sub_and_num_are_ingested_with_vintage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "2016q1.zip"
            make_fsds_zip(zip_path)
            result = ingest_fsds(
                zip_path, Path(tmp) / "out", Path(tmp) / "catalog.json"
            )
            self.assertEqual(result["tables"]["sub"]["rows"], 2)
            self.assertEqual(result["tables"]["num"]["rows"], 2)
            num = pq.read_table(Path(tmp) / "out" / "2016q1" / "num.parquet")
            self.assertIn("source_vintage", num.column_names)
            # Identifier columns stay textual.
            self.assertEqual(num.schema.field("adsh").type, pa.string())

    def test_notes_dataset_is_not_ingested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "2016q1.zip"
            make_fsds_zip(zip_path)
            ingest_fsds(zip_path, Path(tmp) / "out", Path(tmp) / "c.json")
            produced = {p.name for p in (Path(tmp) / "out" / "2016q1").iterdir()}
            self.assertEqual(produced, {"sub.parquet", "num.parquet"})

    def test_reingestion_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "2016q1.zip"
            make_fsds_zip(zip_path)
            out = Path(tmp) / "out"
            ingest_fsds(zip_path, out, Path(tmp) / "c.json")
            again = ingest_fsds(zip_path, out, Path(tmp) / "c.json")
            self.assertTrue(again["tables"]["sub"]["existing"])
            self.assertTrue(again["tables"]["num"]["existing"])


class CompanyFactsTests(unittest.TestCase):
    def test_index_extracts_accession_presence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "companyfacts.zip"
            make_companyfacts_zip(zip_path)
            out = Path(tmp) / "cf.parquet"
            result = index_companyfacts(zip_path, out, Path(tmp) / "c.json")
            self.assertEqual(result["accessions"], 2)
            rows = {r["accession"]: r for r in pq.read_table(out).to_pylist()}
            main_row = rows["0000001234-16-000001"]
            self.assertEqual(main_row["fact_count"], 2)
            self.assertEqual(main_row["taxonomies"], "dei,us-gaap")


class CoverageTests(unittest.TestCase):
    def test_coverage_joins_each_source_to_the_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inventory = pa.Table.from_pylist(
                [
                    {"accession": "0000001234-16-000001", "xbrl_presence": "xbrl"},
                    {"accession": "0000005678-16-000002", "xbrl_presence": "xbrl"},
                    {"accession": "0000000042-10-000001", "xbrl_presence": "none"},
                ]
            )
            inventory_path = Path(tmp) / "inventory.parquet"
            pq.write_table(inventory, inventory_path)

            cf_zip = Path(tmp) / "companyfacts.zip"
            make_companyfacts_zip(cf_zip)
            cf_index = Path(tmp) / "cf.parquet"
            index_companyfacts(cf_zip, cf_index, Path(tmp) / "c.json")

            fsds_zip = Path(tmp) / "2016q1.zip"
            make_fsds_zip(fsds_zip)
            ingest_fsds(fsds_zip, Path(tmp) / "fsds", Path(tmp) / "c.json")

            report = coverage_report(inventory_path, cf_index, Path(tmp) / "fsds")
        self.assertEqual(report["inventory_rows"], 3)
        self.assertEqual(report["companyfacts"]["matched_accessions"], 1)
        self.assertEqual(
            report["companyfacts"]["xbrl_inventory_rows_missing_from_companyfacts"],
            1,
        )
        self.assertEqual(report["fsds"]["distinct_accessions"], 2)
        self.assertEqual(report["fsds"]["matched_to_inventory"], 1)


if __name__ == "__main__":
    unittest.main()
