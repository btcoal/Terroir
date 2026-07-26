"""SEC bulk reconciliation dataset ingestion (UF-022).

Company Facts and the quarterly Financial Statement Data Sets are ingested
as independent checks on our own parsing — never as authoritative
replacements for filings. Every source archive is cataloged with checksum,
size, and retrieval time; loading is idempotent and a new upstream vintage
of the same archive appends a new catalog entry instead of replacing the
old one. The FSDS notes tables are deliberately not ingested toward Gold.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

# FSDS tables ingested for reconciliation. `note`/`txt`/`pre`/`ren` stay out:
# the Notes dataset is not transformed into Release 1 Gold metrics.
FSDS_TABLES = ("sub", "num")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog_source(zip_path: Path, catalog_path: Path) -> dict[str, Any]:
    """Record an archive's identity append-only; keyed by content hash."""
    entries: list[dict[str, Any]] = []
    if catalog_path.exists():
        entries = json.loads(catalog_path.read_text(encoding="utf-8"))
    digest = _sha256_file(zip_path)
    for entry in entries:
        if entry["sha256"] == digest:
            return entry  # same vintage already cataloged
    entry = {
        "file_name": zip_path.name,
        "sha256": digest,
        "size_bytes": zip_path.stat().st_size,
        "retrieved_at": datetime.fromtimestamp(
            zip_path.stat().st_mtime, tz=UTC
        ).isoformat(),
        "cataloged_at": datetime.now(tz=UTC).isoformat(),
        "vintage": f"{zip_path.stem}:{digest[:12]}",
    }
    entries.append(entry)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return entry


def ingest_fsds(zip_path: Path, out_dir: Path, catalog_path: Path) -> dict[str, Any]:
    """Load one FSDS quarter's sub/num tables into vintage-keyed Parquet."""
    entry = catalog_source(zip_path, catalog_path)
    vintage_dir = out_dir / zip_path.stem
    result = {"vintage": entry["vintage"], "tables": {}, "skipped": []}
    vintage_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        members = {Path(n).stem: n for n in archive.namelist()}
        for table in FSDS_TABLES:
            member = members.get(table)
            out_path = vintage_dir / f"{table}.parquet"
            if member is None:
                result["skipped"].append(table)
                continue
            if out_path.exists():  # idempotent
                result["tables"][table] = {
                    "rows": pq.read_metadata(out_path).num_rows,
                    "existing": True,
                }
                continue
            raw = archive.read(member)
            parsed = pacsv.read_csv(
                io.BytesIO(raw),
                parse_options=pacsv.ParseOptions(delimiter="\t"),
                convert_options=pacsv.ConvertOptions(
                    strings_can_be_null=True,
                    # Keep identifiers textual; adsh/cik/tag must not be
                    # reinterpreted numerically.
                    column_types={
                        "adsh": pa.string(),
                        "cik": pa.string(),
                        "tag": pa.string(),
                        "version": pa.string(),
                        "ddate": pa.string(),
                        "period": pa.string(),
                    },
                ),
            )
            source_vintage = pa.array([entry["vintage"]] * parsed.num_rows)
            parsed = parsed.append_column("source_vintage", source_vintage)
            pq.write_table(parsed, out_path)
            result["tables"][table] = {"rows": parsed.num_rows, "existing": False}
    return result


def index_companyfacts(
    zip_path: Path,
    out_parquet: Path,
    catalog_path: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    """Extract the per-accession presence index from Company Facts.

    The raw zip remains the source of truth for values; this index is what
    coverage reporting joins against the accession inventory. Fact rows are
    pulled per-CIK on demand during reconciliation (UF-052).
    """
    entry = catalog_source(zip_path, catalog_path)
    rows: dict[tuple[int, str], dict[str, Any]] = {}
    scanned = 0
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if not name.startswith("CIK") or not name.endswith(".json"):
                continue
            scanned += 1
            if limit is not None and scanned > limit:
                break
            try:
                payload = json.loads(archive.read(name))
                cik = int(payload["cik"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            for taxonomy, tags in (payload.get("facts") or {}).items():
                for _tag, detail in tags.items():
                    for _unit, observations in (detail.get("units") or {}).items():
                        for observation in observations:
                            accession = observation.get("accn")
                            if not accession:
                                continue
                            key = (cik, accession)
                            record = rows.setdefault(
                                key,
                                {
                                    "cik": cik,
                                    "accession": accession,
                                    "form": observation.get("form"),
                                    "fact_count": 0,
                                    "taxonomies": set(),
                                },
                            )
                            record["fact_count"] += 1
                            record["taxonomies"].add(taxonomy)

    table = pa.Table.from_pylist(
        [
            {
                **record,
                "taxonomies": ",".join(sorted(record["taxonomies"])),
                "source_vintage": entry["vintage"],
            }
            for record in rows.values()
        ]
    )
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_parquet)
    return {
        "vintage": entry["vintage"],
        "ciks_scanned": scanned,
        "accessions": table.num_rows,
    }


def coverage_report(
    inventory_parquet: Path,
    companyfacts_index: Path | None,
    fsds_dir: Path | None,
) -> dict[str, Any]:
    """Join each bulk source to the expected accession inventory."""
    import duckdb

    connection = duckdb.connect()
    connection.execute(
        f"CREATE VIEW inventory AS SELECT * FROM read_parquet('{inventory_parquet}')"
    )

    def one_row(query: str) -> tuple[Any, ...]:
        row = connection.sql(query).fetchone()
        assert row is not None
        return row

    report: dict[str, Any] = {
        "inventory_rows": one_row("SELECT count(*) FROM inventory")[0]
    }
    if companyfacts_index is not None and companyfacts_index.exists():
        connection.execute(
            f"CREATE VIEW cf AS SELECT * FROM read_parquet('{companyfacts_index}')"
        )
        matched, unmatched_inventory = one_row(
            """
            SELECT
              (SELECT count(*) FROM inventory i JOIN cf USING (accession)),
              (SELECT count(*) FROM inventory i
                 WHERE i.xbrl_presence IN ('xbrl', 'inline_xbrl')
                   AND NOT EXISTS (SELECT 1 FROM cf WHERE cf.accession = i.accession))
            """
        )
        report["companyfacts"] = {
            "matched_accessions": matched,
            "xbrl_inventory_rows_missing_from_companyfacts": unmatched_inventory,
        }
    if fsds_dir is not None and fsds_dir.exists():
        sub_glob = str(fsds_dir / "*" / "sub.parquet")
        connection.execute(
            f"CREATE VIEW fsds_sub AS SELECT * FROM read_parquet('{sub_glob}')"
        )
        matched, total = one_row(
            """
            SELECT
              (SELECT count(DISTINCT adsh) FROM fsds_sub
                 WHERE adsh IN (SELECT accession FROM inventory)),
              (SELECT count(DISTINCT adsh) FROM fsds_sub)
            """
        )
        report["fsds"] = {
            "distinct_accessions": total,
            "matched_to_inventory": matched,
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fsds = sub.add_parser("ingest-fsds")
    fsds.add_argument("zips", type=Path, nargs="+")
    fsds.add_argument("--out-dir", type=Path, required=True)
    fsds.add_argument("--catalog", type=Path, required=True)

    facts = sub.add_parser("index-companyfacts")
    facts.add_argument("zip", type=Path)
    facts.add_argument("--out", type=Path, required=True)
    facts.add_argument("--catalog", type=Path, required=True)

    coverage = sub.add_parser("coverage")
    coverage.add_argument("--inventory", type=Path, required=True)
    coverage.add_argument("--companyfacts-index", type=Path)
    coverage.add_argument("--fsds-dir", type=Path)

    args = parser.parse_args(argv)
    if args.command == "ingest-fsds":
        for zip_path in args.zips:
            result = ingest_fsds(zip_path, args.out_dir, args.catalog)
            print(json.dumps({"zip": zip_path.name, **result}))
        return 0
    if args.command == "index-companyfacts":
        result = index_companyfacts(args.zip, args.out, args.catalog)
        print(json.dumps(result))
        return 0
    report = coverage_report(args.inventory, args.companyfacts_index, args.fsds_dir)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
