"""Target universe and expected accession inventory (UF-021).

Builds the versioned denominator for acquisition coverage from two
independent discovery sources: the bulk submissions archive (per-CIK JSON
with acceptance datetimes, report periods, and XBRL flags) and quarterly
form indexes. Conflicts between sources are retained and classified, every
row carries its executable-policy eligibility decision (excluded rows are
never dropped), and rebuilding from the same source snapshots produces the
same inventory logical hash.

Per-accession XBRL presence is a first-class column: the UF-010A spike
showed the 2010-2011 mandate phase-in makes early-vintage XBRL absence a
policy matter, not an acquisition defect.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from us_fundamentals.eligibility import ReleasePolicy
from us_fundamentals.logical_hash import logical_hash

TARGET_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})

INVENTORY_KEY = ["accession"]

_COLUMNS = [
    "accession",
    "cik",
    "form",
    "is_amendment",
    "report_period",
    "filing_date",
    "sec_acceptance_datetime",
    "is_xbrl",
    "is_inline_xbrl",
    "primary_document",
    "discovery_sources",
    "conflicts",
    "eligibility_status",
    "eligibility_reasons",
    "eligibility_policy_version",
    "xbrl_presence",
]


def parse_form_idx(text: str, source_label: str) -> list[dict[str, Any]]:
    """Rows from one quarterly form.idx. Company names may contain runs of
    spaces, so fields are parsed from the right."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] in TARGET_FORMS and parts[-1].endswith(".txt"):
            try:
                cik = int(parts[-3])
            except ValueError:
                continue
            rows.append(
                {
                    "accession": Path(parts[-1]).stem,
                    "cik": cik,
                    "form": parts[0],
                    "filing_date": parts[-2],
                    "source": source_label,
                }
            )
    return rows


def iter_submissions_filings(zip_path: Path) -> Any:
    """Yield target-form filing records from the bulk submissions archive.

    Handles both the primary CIK##########.json files (columnar `recent`
    plus references to paging files) and the paging files themselves
    (columnar at top level).
    """
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if not name.endswith(".json") or name == "placeholder.txt":
                continue
            try:
                payload = json.loads(archive.read(name))
            except (json.JSONDecodeError, KeyError):
                continue
            if "filings" in payload:  # primary file
                cik = int(payload["cik"])
                block = payload["filings"].get("recent", {})
            elif "accessionNumber" in payload:  # paging file: CIK from name
                stem = Path(name).name
                digits = "".join(c for c in stem if c.isdigit())[:10]
                if not digits:
                    continue
                cik = int(digits)
                block = payload
            else:
                continue
            yield from _columnar_filings(cik, block)


def _columnar_filings(cik: int, block: dict[str, Any]) -> Any:
    forms = block.get("form", [])
    for i, form in enumerate(forms):
        if form not in TARGET_FORMS:
            continue

        def col(key: str, index: int = i) -> Any:
            values = block.get(key, [])
            return values[index] if index < len(values) else None

        yield {
            "accession": col("accessionNumber"),
            "cik": cik,
            "form": form,
            "filing_date": col("filingDate"),
            "report_period": col("reportDate") or None,
            "sec_acceptance_datetime": col("acceptanceDateTime"),
            "is_xbrl": bool(col("isXBRL")),
            "is_inline_xbrl": bool(col("isInlineXBRL")),
            "primary_document": col("primaryDocument") or None,
            "source": "bulk_submissions",
        }


def build_inventory(
    submission_records: list[dict[str, Any]],
    index_records: list[dict[str, Any]],
    policy: ReleasePolicy,
) -> pa.Table:
    """Merge discovery sources into the normalized inventory table."""
    merged: dict[str, dict[str, Any]] = {}
    sources: dict[str, list[str]] = defaultdict(list)
    conflicts: dict[str, list[dict[str, str]]] = defaultdict(list)

    for record in submission_records:
        accession = record["accession"]
        if accession is None:
            continue
        merged[accession] = dict(record)
        sources[accession].append(record["source"])

    for record in index_records:
        accession = record["accession"]
        sources[accession].append(record["source"])
        existing = merged.get(accession)
        if existing is None:
            merged[accession] = {
                "accession": accession,
                "cik": record["cik"],
                "form": record["form"],
                "filing_date": record["filing_date"],
                "report_period": None,
                "sec_acceptance_datetime": None,
                "is_xbrl": None,
                "is_inline_xbrl": None,
                "primary_document": None,
                "source": record["source"],
            }
            continue
        # Conflict classification: same accession, disagreeing fields.
        for field, kind in (
            ("form", "form_mismatch"),
            ("cik", "cik_mismatch"),
            ("filing_date", "filing_date_mismatch"),
        ):
            if existing.get(field) != record.get(field):
                conflicts[accession].append(
                    {
                        "kind": kind,
                        "bulk_submissions": str(existing.get(field)),
                        record["source"]: str(record.get(field)),
                    }
                )

    rows = []
    for accession in sorted(merged):
        record = merged[accession]
        decision = policy.evaluate(
            {
                "accession": accession,
                "form": record.get("form"),
                "sec_acceptance_datetime": record.get("sec_acceptance_datetime"),
                # Issuer classification arrives with the security master;
                # the policy reports these as missing, never as excluded.
                "accounting_standard": None,
                "registrant_type": None,
                "issuer_type": None,
            }
        )
        is_xbrl = record.get("is_xbrl")
        inline = record.get("is_inline_xbrl")
        if is_xbrl is None and inline is None:
            presence = "unknown"
        elif inline:
            presence = "inline_xbrl"
        elif is_xbrl:
            presence = "xbrl"
        else:
            presence = "none"
        rows.append(
            {
                "accession": accession,
                "cik": record.get("cik"),
                "form": record.get("form"),
                "is_amendment": str(record.get("form", "")).endswith("/A"),
                "report_period": record.get("report_period"),
                "filing_date": record.get("filing_date"),
                "sec_acceptance_datetime": record.get("sec_acceptance_datetime"),
                "is_xbrl": is_xbrl,
                "is_inline_xbrl": inline,
                "primary_document": record.get("primary_document"),
                "discovery_sources": json.dumps(sorted(set(sources[accession]))),
                "conflicts": json.dumps(conflicts.get(accession, [])),
                "eligibility_status": decision.eligibility_status,
                "eligibility_reasons": json.dumps(list(decision.reason_codes)),
                "eligibility_policy_version": decision.policy_version,
                "xbrl_presence": presence,
            }
        )
    return pa.Table.from_pylist(rows).select(_COLUMNS)


def inventory_hash(table: pa.Table) -> str:
    return logical_hash(table, INVENTORY_KEY)


def taxonomy_coverage_report(
    table: pa.Table, cache_manifest_path: Path, vintage_list_path: Path
) -> dict[str, Any]:
    """UF-021 coverage check against the UF-013 published-vintage superset.

    A filing's referenced standard-taxonomy vintage is definitively known
    only at parse time; before that, a filing filed in year Y can reference
    vintages in [Y-2, Y]. The check verifies the cache covers that band for
    every XBRL-bearing filing year and reports gaps. A reported gap is a
    defect in the UF-013 vintage list, not a redefinition of the cache.
    """
    manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
    listing = json.loads(vintage_list_path.read_text(encoding="utf-8"))
    cached = {(p["family"], p["vintage"]) for p in manifest["packages"]}
    documented_gaps: set[tuple[str, int]] = set()
    for gap in listing.get("known_gaps", []):
        if isinstance(gap.get("vintages"), list):
            for vintage in gap["vintages"]:
                for family in str(gap["family"]).split("/"):
                    documented_gaps.add((family, vintage))

    filing_years = sorted(
        {
            int(str(row["filing_date"])[:4])
            for row in table.to_pylist()
            if row["filing_date"]
            and row["xbrl_presence"] in ("xbrl", "inline_xbrl")
            # Excluded rows (e.g. pre-2010 voluntary-program filings) stay in
            # the inventory but are outside the Release 1 parse denominator.
            and row["eligibility_status"] != "excluded"
        }
    )
    missing: list[dict[str, Any]] = []
    for year in filing_years:
        for candidate in range(year - 2, year + 1):
            key = ("us-gaap", candidate)
            if key not in cached:
                missing.append(
                    {
                        "family": "us-gaap",
                        "vintage": candidate,
                        "referenced_by_filing_year": year,
                        "documented_gap": key in documented_gaps,
                    }
                )
    undocumented = [m for m in missing if not m["documented_gap"]]
    return {
        "xbrl_filing_years": filing_years,
        "missing_vintages": missing,
        "undocumented_missing": undocumented,
        "ok": not undocumented,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submissions-zip", type=Path, required=True)
    parser.add_argument(
        "--index-dir",
        type=Path,
        required=True,
        help="directory of <year>-QTR<q>-form.idx files",
    )
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    policy = ReleasePolicy.from_file(args.policy)
    submission_records = list(iter_submissions_filings(args.submissions_zip))
    index_records = []
    for idx_path in sorted(args.index_dir.glob("*.idx")):
        index_records.extend(
            parse_form_idx(
                idx_path.read_text(encoding="latin-1"),
                f"form_index:{idx_path.stem}",
            )
        )
    table = build_inventory(submission_records, index_records, policy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, args.out)
    print(
        json.dumps(
            {
                "rows": table.num_rows,
                "logical_hash": inventory_hash(table),
                "out": str(args.out),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
