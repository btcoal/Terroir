from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.bronze import (  # noqa: E402
    AccessionManifest,
    BronzeStore,
    ObjectStore,
    sha256_bytes,
)
from us_fundamentals.errors import IntegrityError, MalformedInputError  # noqa: E402

ACCESSION = "0000000001-16-000001"

# A synthetic parser-input closure covering every required member kind.
CLOSURE = {
    "index.json": ("filing_index", b'{"directory": {"item": []}}'),
    "acme-10k.htm": ("primary_document", b"<html>10-K primary</html>"),
    "acme-20161231.xml": ("instance", b"<xbrl>instance</xbrl>"),
    "acme-20161231.xsd": ("extension_schema", b"<schema/>"),
    "acme-20161231_cal.xml": ("linkbase", b"<calculationLink/>"),
    "acme-20161231_def.xml": ("linkbase", b"<definitionLink/>"),
    "acme-20161231_pre.xml": ("linkbase", b"<presentationLink/>"),
    "acme-20161231_lab.xml": ("label", b"<labelLink/>"),
    "acme-20161231_ref.xml": ("reference", b"<referenceLink/>"),
    "0000000001-16-000001.hdr.sgml": ("filing_header", b"<SEC-HEADER/>"),
    "ext-dep.xsd": ("external", b"<schema>consumed external</schema>"),
}


def populate(store: BronzeStore) -> None:
    for name, (role, content) in CLOSURE.items():
        store.add_object(
            ACCESSION,
            1234,
            name,
            role,
            f"https://www.sec.gov/Archives/x/{name}",
            content,
            content_type="application/octet-stream",
        )


class ObjectStoreTests(unittest.TestCase):
    def test_put_is_idempotent_and_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(Path(tmp))
            first = store.put_bytes(b"same bytes")
            second = store.put_bytes(b"same bytes")
            self.assertEqual(first, second)
            self.assertEqual(store.get(first), b"same bytes")

    def test_corrupted_object_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(Path(tmp))
            digest = store.put_bytes(b"original")
            store._path(digest).write_bytes(b"tampered")
            self.assertFalse(store.verify(digest))
            with self.assertRaises(IntegrityError):
                store.get(digest)


class BronzeStoreTests(unittest.TestCase):
    def test_manifest_records_required_fields_per_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BronzeStore(Path(tmp))
            populate(store)
            manifest = store.load_manifest(ACCESSION)
            assert manifest is not None
            self.assertEqual(len(manifest.entries), len(CLOSURE))
            for name, (role, content) in CLOSURE.items():
                entry = manifest.entries[name]
                self.assertEqual(entry.role, role)
                self.assertEqual(entry.sha256, sha256_bytes(content))
                self.assertEqual(entry.size_bytes, len(content))
                self.assertTrue(entry.source_url.startswith("https://www.sec.gov/"))
                self.assertIsNotNone(entry.retrieved_at)
                self.assertIsNotNone(entry.content_type)

    def test_reacquiring_identical_bytes_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BronzeStore(Path(tmp))
            populate(store)
            entry = store.add_object(
                ACCESSION,
                1234,
                "acme-20161231.xml",
                "instance",
                "https://www.sec.gov/Archives/x/acme-20161231.xml",
                CLOSURE["acme-20161231.xml"][1],
            )
            self.assertEqual(entry.sha256, sha256_bytes(b"<xbrl>instance</xbrl>"))

    def test_hash_mismatch_is_terminal_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BronzeStore(Path(tmp))
            populate(store)
            original_digest = sha256_bytes(CLOSURE["acme-20161231.xml"][1])
            with self.assertRaises(IntegrityError) as ctx:
                store.add_object(
                    ACCESSION,
                    1234,
                    "acme-20161231.xml",
                    "instance",
                    "https://www.sec.gov/Archives/x/acme-20161231.xml",
                    b"<xbrl>DIFFERENT bytes</xbrl>",
                )
            self.assertEqual(ctx.exception.category, "terminal.integrity")
            # The prior object and manifest entry are untouched.
            manifest = store.load_manifest(ACCESSION)
            assert manifest is not None
            self.assertEqual(
                manifest.entries["acme-20161231.xml"].sha256, original_digest
            )
            self.assertEqual(
                store.objects.get(original_digest), b"<xbrl>instance</xbrl>"
            )

    def test_storage_classes_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BronzeStore(Path(tmp))
            populate(store)
            store.add_reference(
                ACCESSION,
                1234,
                "giant-exhibit-99.htm",
                "external",
                "https://www.sec.gov/Archives/x/giant-exhibit-99.htm",
            )
            manifest = store.load_manifest(ACCESSION)
            assert manifest is not None
            classes = {e.storage_class for e in manifest.entries.values()}
            self.assertIn("stored", classes)
            self.assertIn("reference_only", classes)
            with self.assertRaises(MalformedInputError):
                AccessionManifest.from_json(
                    manifest.to_json().replace('"stored"', '"warm"', 1)
                )

    def test_restore_is_offline_and_hash_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BronzeStore(Path(tmp) / "bronze")
            populate(store)
            store.add_reference(
                ACCESSION,
                1234,
                "ref-only.htm",
                "external",
                "https://www.sec.gov/Archives/x/ref-only.htm",
            )
            dest = Path(tmp) / "restored"

            # Disable network access for the duration of the restore.
            def refuse(*args: object, **kwargs: object) -> None:
                raise AssertionError("restore attempted network access")

            original_socket = socket.socket
            socket.socket = refuse  # type: ignore[misc,assignment]
            try:
                restored = store.restore(ACCESSION, dest)
            finally:
                socket.socket = original_socket  # type: ignore[misc]

            self.assertEqual(restored, sorted(CLOSURE))  # reference_only skipped
            for name, (_, content) in CLOSURE.items():
                self.assertEqual((dest / name).read_bytes(), content)

    def test_verify_accession_reports_per_object_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BronzeStore(Path(tmp))
            populate(store)
            health = store.verify_accession(ACCESSION)
            self.assertTrue(all(health.values()))
            digest = sha256_bytes(CLOSURE["acme-10k.htm"][1])
            store.objects._path(digest).write_bytes(b"bitrot")
            health = store.verify_accession(ACCESSION)
            self.assertFalse(health["acme-10k.htm"])
            self.assertTrue(health["acme-20161231.xml"])


if __name__ == "__main__":
    unittest.main()
