from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.eligibility import ReleasePolicy  # noqa: E402
from us_fundamentals.inventory import (  # noqa: E402
    build_inventory,
    inventory_hash,
    iter_submissions_filings,
    parse_form_idx,
)

POLICY = ReleasePolicy.from_file(
    PROJECT_ROOT / "config" / "release_1_issuer_universe.json"
)

FORM_IDX = """Form Type   Company Name        CIK         Date Filed  File Name
10-K        ACME CORP           1234        2016-02-20  edgar/data/1234/0000001234-16-000001.txt
10-Q        WIDGET  NO 10 LTD   5678        2016-05-01  edgar/data/5678/0000005678-16-000002.txt
8-K         NOISE CO            9999        2016-05-02  edgar/data/9999/0000009999-16-000003.txt
10-K/A      ACME CORP           1234        2016-06-15  edgar/data/1234/0000001234-16-000004.txt
"""

SUBMISSIONS = {
    "cik": 1234,
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000001234-16-000001",
                "0000001234-16-000004",
                "0000001234-09-000009",
            ],
            "form": ["10-K", "10-K/A", "10-K"],
            "filingDate": ["2016-02-20", "2016-06-15", "2009-03-01"],
            "reportDate": ["2015-12-31", "2015-12-31", "2008-12-31"],
            "acceptanceDateTime": [
                "2016-02-20T16:31:00.000Z",
                "2016-06-15T09:12:00.000Z",
                "2009-03-01T12:00:00.000Z",
            ],
            "isXBRL": [1, 1, 0],
            "isInlineXBRL": [0, 0, 0],
            "primaryDocument": ["acme-10k.htm", "acme-10ka.htm", "acme09.txt"],
        }
    },
}


def submissions_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CIK0000001234.json", json.dumps(SUBMISSIONS))
    return buffer.getvalue()


class FormIdxTests(unittest.TestCase):
    def test_parses_target_forms_and_skips_noise(self) -> None:
        rows = parse_form_idx(FORM_IDX, "form_index:2016-QTR2")
        self.assertEqual(
            [r["accession"] for r in rows],
            [
                "0000001234-16-000001",
                "0000005678-16-000002",
                "0000001234-16-000004",
            ],
        )

    def test_company_names_with_inner_runs_of_spaces_parse(self) -> None:
        rows = parse_form_idx(FORM_IDX, "s")
        widget = rows[1]
        self.assertEqual(widget["cik"], 5678)
        self.assertEqual(widget["filing_date"], "2016-05-01")


class InventoryTests(unittest.TestCase):
    def _build(self, index_text: str = FORM_IDX):
        with zipfile.ZipFile(io.BytesIO(submissions_zip_bytes())) as _:
            pass
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "submissions.zip"
            zip_path.write_bytes(submissions_zip_bytes())
            submission_records = list(iter_submissions_filings(zip_path))
        index_records = parse_form_idx(index_text, "form_index:2016-QTR2")
        return build_inventory(submission_records, index_records, POLICY)

    def test_every_required_field_is_recorded(self) -> None:
        table = self._build()
        row = next(
            r for r in table.to_pylist() if r["accession"] == "0000001234-16-000001"
        )
        self.assertEqual(row["cik"], 1234)
        self.assertEqual(row["form"], "10-K")
        self.assertFalse(row["is_amendment"])
        self.assertEqual(row["report_period"], "2015-12-31")
        self.assertEqual(row["filing_date"], "2016-02-20")
        self.assertEqual(row["sec_acceptance_datetime"], "2016-02-20T16:31:00.000Z")
        self.assertEqual(
            json.loads(row["discovery_sources"]),
            ["bulk_submissions", "form_index:2016-QTR2"],
        )
        self.assertEqual(row["xbrl_presence"], "xbrl")

    def test_amendments_are_flagged(self) -> None:
        table = self._build()
        amendment = next(
            r for r in table.to_pylist() if r["accession"] == "0000001234-16-000004"
        )
        self.assertTrue(amendment["is_amendment"])

    def test_index_only_accessions_are_kept_with_unknown_xbrl(self) -> None:
        table = self._build()
        index_only = next(
            r for r in table.to_pylist() if r["accession"] == "0000005678-16-000002"
        )
        self.assertEqual(index_only["xbrl_presence"], "unknown")
        self.assertIsNone(index_only["sec_acceptance_datetime"])
        self.assertEqual(index_only["eligibility_status"], "indeterminate")

    def test_conflicting_sources_are_retained_and_classified(self) -> None:
        conflicted = FORM_IDX.replace(
            "10-K        ACME CORP           1234        2016-02-20",
            "10-Q        ACME CORP           1234        2016-02-20",
        )
        table = self._build(conflicted)
        row = next(
            r for r in table.to_pylist() if r["accession"] == "0000001234-16-000001"
        )
        kinds = {c["kind"] for c in json.loads(row["conflicts"])}
        self.assertIn("form_mismatch", kinds)
        # The row survives with both sources recorded.
        self.assertEqual(len(json.loads(row["discovery_sources"])), 2)

    def test_excluded_rows_are_annotated_never_dropped(self) -> None:
        table = self._build()
        early = next(
            r for r in table.to_pylist() if r["accession"] == "0000001234-09-000009"
        )
        self.assertEqual(early["eligibility_status"], "excluded")
        self.assertIn("before_release_start", json.loads(early["eligibility_reasons"]))
        self.assertEqual(early["eligibility_policy_version"], "1.0.0")
        self.assertEqual(early["xbrl_presence"], "none")

    def test_rebuild_from_same_sources_reproduces_the_logical_hash(self) -> None:
        first = self._build()
        second = self._build()
        self.assertEqual(inventory_hash(first), inventory_hash(second))

    def test_hash_changes_when_a_source_row_changes(self) -> None:
        first = self._build()
        second = self._build(FORM_IDX.replace("2016-05-01", "2016-05-02"))
        self.assertNotEqual(inventory_hash(first), inventory_hash(second))


if __name__ == "__main__":
    unittest.main()
