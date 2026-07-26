from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import psycopg  # noqa: E402

from pg_cluster import scratch_dsn  # noqa: E402
from us_fundamentals.migrations import (  # noqa: E402
    applied_versions,
    load_migrations,
    migrate_down,
    migrate_up,
)

DSN = scratch_dsn()

EXPECTED_TABLES = {
    "entity",
    "entity_history",
    "security",
    "listing",
    "filing",
    "accession_object",
    "xbrl_context",
    "xbrl_unit",
    "raw_fact",
    "taxonomy_relationship",
    "mapping_rule",
    "canonical_observation",
    "comparability_event",
    "qc_result",
    "review_item",
    "dataset_release",
    "run_record",
}

FILING_ROW = """
INSERT INTO filing (accession, cik, form, filing_date, sec_acceptance_datetime,
                    eligibility_status, eligibility_policy_version, ingestion_status)
VALUES ('0000000001-24-000001', 1234, '10-K', '2024-02-01',
        '2024-02-01T16:31:00-05:00', 'eligible', '1.0.0', 'acquired')
"""


def tables(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    return {row[0] for row in rows} - {"schema_migrations"}


@unittest.skipIf(DSN is None, "no PostgreSQL available for migration tests")
class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = psycopg.connect(DSN)
        self.conn.autocommit = True
        migrate_down(self.conn)  # start from a clean slate every test

    def tearDown(self) -> None:
        migrate_down(self.conn)
        self.conn.close()

    def _populate(self) -> None:
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO entity (entity_id, cik) VALUES ('ent_1', 1234)"
            )
            self.conn.execute(
                """
                INSERT INTO entity_history (entity_id, attribute, value, valid_from,
                                            source_kind, source_ref, confidence)
                VALUES ('ent_1', 'legal_name', 'Acme Corp',
                        '2010-01-01T00:00:00Z', 'accession', '0000000001-24-000001', 1.0)
                """
            )
            self.conn.execute(
                """
                INSERT INTO security (security_id, entity_id, title, share_class)
                VALUES ('sec_1', 'ent_1', 'Common Stock', 'A')
                """
            )
            self.conn.execute(FILING_ROW)
            self.conn.execute(
                """
                INSERT INTO xbrl_context (accession, context_id, entity_identifier,
                                          period_type, period_instant)
                VALUES ('0000000001-24-000001', 'c1', '0000001234',
                        'instant', '2023-12-31')
                """
            )
            self.conn.execute(
                """
                INSERT INTO raw_fact (accession, concept_qname, concept_ns,
                                      is_extension, context_id, value_numeric,
                                      decimals_raw, source_document)
                VALUES ('0000000001-24-000001', 'us-gaap:Assets',
                        'http://fasb.org/us-gaap/2023', false, 'c1',
                        1000000, '-3', 'acme-20231231.htm')
                """
            )

    def test_forward_from_empty_creates_all_tables(self) -> None:
        ran = migrate_up(self.conn)
        self.assertEqual(len(ran), len(load_migrations()))
        self.assertEqual(tables(self.conn), EXPECTED_TABLES)

    def test_forward_then_rollback_on_empty_database(self) -> None:
        migrate_up(self.conn)
        migrate_down(self.conn)
        self.assertEqual(tables(self.conn), set())
        self.assertEqual(applied_versions(self.conn), [])

    def test_rollback_and_reapply_against_populated_database(self) -> None:
        migrate_up(self.conn)
        self._populate()
        rolled = migrate_down(self.conn)
        self.assertEqual(len(rolled), len(load_migrations()))
        self.assertEqual(tables(self.conn), set())
        ran = migrate_up(self.conn)  # forward again after a populated rollback
        self.assertEqual(len(ran), len(load_migrations()))
        self.assertEqual(tables(self.conn), EXPECTED_TABLES)

    def test_migrations_are_idempotent_per_version(self) -> None:
        migrate_up(self.conn)
        self.assertEqual(migrate_up(self.conn), [])

    def test_duplicate_raw_facts_are_preserved(self) -> None:
        migrate_up(self.conn)
        self._populate()
        with self.conn.transaction():
            self.conn.execute(
                """
                INSERT INTO raw_fact (accession, concept_qname, concept_ns,
                                      is_extension, context_id, value_numeric,
                                      decimals_raw, source_document, duplicate_class)
                VALUES ('0000000001-24-000001', 'us-gaap:Assets',
                        'http://fasb.org/us-gaap/2023', false, 'c1',
                        1000000, '-3', 'acme-20231231.htm', 'consistent_duplicate')
                """
            )
        count = self.conn.execute(
            "SELECT count(*) FROM raw_fact WHERE concept_qname = 'us-gaap:Assets'"
        ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_unresolved_duplicate_canonical_versions_are_rejected(self) -> None:
        migrate_up(self.conn)
        self._populate()
        insert = """
            INSERT INTO canonical_observation
                (dataset_version, accession, entity_id, metric_id,
                 fiscal_period_id, value, reported_unit, derivation_type,
                 information_available_at)
            VALUES ('ds-1', '0000000001-24-000001', 'ent_1', 'assets_total',
                    'FY2023', 1000000, 'USD', 'direct',
                    '2024-02-01T16:32:30-05:00')
        """
        with self.conn.transaction():
            self.conn.execute(insert)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.conn.transaction():
                self.conn.execute(insert)

    def test_overlapping_listings_are_rejected_without_multi_listing_rule(
        self,
    ) -> None:
        migrate_up(self.conn)
        self._populate()
        base = """
            INSERT INTO listing (security_id, ticker, exchange, valid_from,
                                 valid_to, inference_rule_version, confidence,
                                 allow_multi_listing)
            VALUES ('sec_1', %s, 'XNYS', %s, %s, 'r1', 0.9, %s)
        """
        with self.conn.transaction():
            self.conn.execute(base, ("ACME", "2010-01-01", "2015-06-30", False))
        with self.assertRaises(psycopg.errors.ExclusionViolation):
            with self.conn.transaction():
                self.conn.execute(base, ("ACM2", "2015-01-01", None, False))
        with self.conn.transaction():  # explicit multi-listing rule permits it
            self.conn.execute(base, ("ACM2", "2015-01-01", None, True))

    def test_filing_time_and_status_contracts_are_enforced(self) -> None:
        migrate_up(self.conn)
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.conn.transaction():
                self.conn.execute(
                    FILING_ROW.replace("'eligible'", "'maybe'").replace(
                        "0000000001-24-000001", "0000000001-24-000002"
                    )
                )
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.conn.transaction():
                self.conn.execute(
                    FILING_ROW.replace("'acquired'", "'lost'").replace(
                        "0000000001-24-000001", "0000000001-24-000003"
                    )
                )


if __name__ == "__main__":
    unittest.main()
