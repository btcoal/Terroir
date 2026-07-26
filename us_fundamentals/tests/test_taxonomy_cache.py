from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.errors import ContractViolationError  # noqa: E402
from us_fundamentals.taxonomy_cache import (  # noqa: E402
    PINNED_MANIFEST_PATH,
    VINTAGE_LIST_PATH,
    load_catalog,
    load_offline,
    resolve_offline,
    verify_cache,
)

CACHE_DIR = PROJECT_ROOT / "data" / "taxonomy_packages"
CACHE_BUILT = (CACHE_DIR / "cache_manifest.json").exists()


class VintageListTests(unittest.TestCase):
    """Structural checks on the committed superset list; always run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.listing = json.loads(VINTAGE_LIST_PATH.read_text(encoding="utf-8"))

    def test_list_is_versioned(self) -> None:
        self.assertIn("list_version", self.listing)
        self.assertIn("schema_version", self.listing)

    def test_every_required_family_is_present(self) -> None:
        families = {p["family"] for p in self.listing["packages"]}
        for family in ("us-gaap", "srt", "dei", "country", "currency", "exch", "stpr"):
            self.assertIn(family, families)

    def test_us_gaap_covers_2011_through_current(self) -> None:
        vintages = {
            p["vintage"] for p in self.listing["packages"] if p["family"] == "us-gaap"
        }
        self.assertEqual(vintages, set(range(2011, 2027)))

    def test_known_gaps_are_documented_not_silent(self) -> None:
        gaps = self.listing["known_gaps"]
        self.assertTrue(any("us-gaap" in g["family"] for g in gaps))
        for gap in gaps:
            self.assertTrue(gap["reason"].strip())

    def test_only_sec_and_fasb_hosts(self) -> None:
        for package in self.listing["packages"]:
            self.assertRegex(
                package["url"], r"^https://(xbrl\.fasb\.org|xbrl\.sec\.gov)/"
            )


@unittest.skipIf(not PINNED_MANIFEST_PATH.exists(), "cache manifest not pinned")
class PinnedManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(PINNED_MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_every_package_is_hash_pinned(self) -> None:
        for package in self.manifest["packages"]:
            self.assertRegex(package["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(package["size_bytes"], 0)

    def test_modern_packages_pin_their_uri_catalog(self) -> None:
        with_catalog = [p for p in self.manifest["packages"] if p["catalog_sha256"]]
        self.assertGreater(len(with_catalog), 15)
        for package in with_catalog:
            self.assertRegex(package["catalog_sha256"], r"^[0-9a-f]{64}$")

    def test_every_package_has_rewrites_and_an_entry_point(self) -> None:
        for package in self.manifest["packages"]:
            self.assertTrue(package["rewrites"], package["file_name"])
            self.assertTrue(package["entry_point"], package["file_name"])

    def test_core_spec_schemas_are_mirrored_and_pinned(self) -> None:
        core = self.manifest["core_schemas"]["files"]
        urls = {f["url"] for f in core}
        self.assertTrue(any("xbrl-instance-2003-12-31.xsd" in u for u in urls), urls)
        for entry in core:
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")


@unittest.skipIf(not CACHE_BUILT, "taxonomy cache not built locally")
class OfflineLoadTests(unittest.TestCase):
    """The UF-013 acceptance test: earliest, middle, latest vintages load
    fully offline, and unresolvable URIs fail closed with the URI named."""

    @classmethod
    def setUpClass(cls) -> None:
        manifest = json.loads(
            (CACHE_DIR / "cache_manifest.json").read_text(encoding="utf-8")
        )
        cls.entry_points = {
            f"{p['family']}{p['vintage']}": p["entry_point"]
            for p in manifest["packages"]
        }

    def test_cache_matches_pinned_manifest(self) -> None:
        self.assertEqual(verify_cache(CACHE_DIR), [])

    def test_earliest_middle_latest_vintages_load_offline(self) -> None:
        for key, minimum_concepts in (
            ("us-gaap2011", 10000),
            ("us-gaap2018", 10000),
            ("us-gaap2026", 10000),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                result = load_offline(self.entry_points[key], CACHE_DIR, Path(tmp))
            self.assertGreater(result["concepts"], minimum_concepts, key)
            self.assertEqual(result["errors"], [], key)

    def test_unresolvable_uri_fails_closed_and_names_the_uri(self) -> None:
        bogus = "https://xbrl.fasb.org/us-gaap/1999/us-gaap-1999.xsd"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ContractViolationError) as ctx:
                load_offline(bogus, CACHE_DIR, Path(tmp))
        self.assertIn(bogus, ctx.exception.context["unresolved_uris"])

    def test_resolver_prefers_longest_prefix_and_requires_existence(self) -> None:
        catalog = load_catalog(CACHE_DIR)
        mapped = resolve_offline(
            "https://xbrl.fasb.org/us-gaap/2018/elts/us-gaap-2018-01-31.xsd",
            catalog,
        )
        self.assertIsNotNone(mapped)
        self.assertTrue(str(mapped).endswith("us-gaap-2018-01-31.xsd"))
        self.assertIsNone(
            resolve_offline("https://example.com/not-a-taxonomy.xsd", catalog)
        )


if __name__ == "__main__":
    unittest.main()
