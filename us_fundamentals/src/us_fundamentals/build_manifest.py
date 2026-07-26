"""Deterministic release manifests (UF-014, ADR-0007).

A release manifest pins everything that determines a dataset's logical
content: the accession set with per-accession raw-object hashes, the
taxonomy package pins, every component version, the code commit, and the
logical hash of each output table. Rebuilding from the same manifest must
reproduce the same logical hashes (ADR-0008).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from us_fundamentals.bronze import BronzeStore
from us_fundamentals.logical_hash import (
    NORMALIZATION_SPEC_VERSION,
    logical_hash_parquet,
)

MANIFEST_SCHEMA_VERSION = 1


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except OSError:
        return "unknown"


def accession_pins(bronze: BronzeStore, accessions: list[str]) -> list[dict[str, Any]]:
    """Per-accession raw-object hash set, from Bronze manifests."""
    pins = []
    for accession in sorted(accessions):
        manifest = bronze.load_manifest(accession)
        if manifest is None:
            raise FileNotFoundError(f"no Bronze manifest for {accession}")
        pins.append(
            {
                "accession": accession,
                "objects": {
                    e.file_name: e.sha256
                    for e in sorted(
                        manifest.entries.values(), key=lambda e: e.file_name
                    )
                    if e.sha256 is not None
                },
            }
        )
    return pins


def create_release_manifest(
    dataset_version: str,
    bronze: BronzeStore,
    accessions: list[str],
    output_tables: dict[str, tuple[Path, list[str]]],
    component_versions: dict[str, str],
    taxonomy_manifest_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Assemble and return the pinned release manifest.

    output_tables maps table name -> (parquet path, primary key columns).
    component_versions must include parser, mapping, qc_rules, and formulas.
    """
    required = {"parser", "mapping", "qc_rules", "formulas"}
    missing = required.difference(component_versions)
    if missing:
        raise ValueError(f"component_versions missing: {sorted(missing)}")

    taxonomy = json.loads(taxonomy_manifest_path.read_text(encoding="utf-8"))
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "built_at": datetime.now(tz=UTC).isoformat(),
        "code_commit": _git_commit(repo_root),
        "component_versions": dict(sorted(component_versions.items())),
        "normalization_spec_version": NORMALIZATION_SPEC_VERSION,
        "taxonomy_packages": [
            {
                "file_name": p["file_name"],
                "sha256": p["sha256"],
                "catalog_sha256": p["catalog_sha256"],
            }
            for p in taxonomy["packages"]
        ],
        "taxonomy_vintage_list_version": taxonomy["vintage_list_version"],
        "accessions": accession_pins(bronze, accessions),
        "tables": {
            name: {
                "path": str(path),
                "primary_key": key,
                "logical_hash": logical_hash_parquet(path, key),
            }
            for name, (path, key) in sorted(output_tables.items())
        },
    }
    # Self-hash over logical content only: the build timestamp and physical
    # output paths may differ between two otherwise identical builds.
    hashable = {k: v for k, v in manifest.items() if k != "built_at"}
    hashable["tables"] = {
        name: {"primary_key": t["primary_key"], "logical_hash": t["logical_hash"]}
        for name, t in manifest["tables"].items()
    }
    manifest["manifest_content_sha256"] = hashlib.sha256(
        json.dumps(hashable, sort_keys=True).encode()
    ).hexdigest()
    return manifest


def compare_manifests(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Table-level equivalence report between two release manifests."""
    tables = sorted(set(left["tables"]) | set(right["tables"]))
    report = {}
    for name in tables:
        l_hash = left["tables"].get(name, {}).get("logical_hash")
        r_hash = right["tables"].get(name, {}).get("logical_hash")
        report[name] = {
            "equivalent": l_hash == r_hash and l_hash is not None,
            "left": l_hash,
            "right": r_hash,
        }
    return {
        "content_identical": left.get("manifest_content_sha256")
        == right.get("manifest_content_sha256"),
        "tables": report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    args = parser.parse_args(argv)

    left = json.loads(args.left.read_text(encoding="utf-8"))
    right = json.loads(args.right.read_text(encoding="utf-8"))
    report = compare_manifests(left, right)
    print(json.dumps(report, indent=2))
    return 0 if report["content_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
