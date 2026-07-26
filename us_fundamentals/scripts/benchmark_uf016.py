"""UF-016 Parquet/DuckDB physical-layout benchmark.

Reproducible benchmark code behind ADR-0009. The synthetic generator derives
its cardinality from the real UF-021 accession inventory — entity count,
accessions per entity, filings per year, amendment rate — and records the
inventory identity it used. Three candidate layouts are measured against a
PIT `as_of` query over an effective-interval table, a metric cross-section,
and a company-history projection, plus incremental write cost.

Run:  uv run python scripts/benchmark_uf016.py \
          --inventory data/inventory/accession_inventory.parquet \
          --out data/benchmarks/uf016
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import time
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

METRICS = [f"metric_{i:02d}" for i in range(25)]
METRIC_GROUPS = {m: f"group_{int(m.split('_')[1]) % 4}" for m in METRICS}

SORTS = {
    "pit_sort": "metric_id, entity_id, available_at, fiscal_period_end",
    "history_sort": "entity_id, metric_id, available_at",
}


def cardinality_profile(inventory_path: Path) -> dict:
    connection = duckdb.connect()
    row = connection.sql(
        f"""
        SELECT
          count(*) FILTER (WHERE eligibility_status != 'excluded'),
          count(DISTINCT cik) FILTER (WHERE eligibility_status != 'excluded'),
          avg(CASE WHEN is_amendment THEN 1 ELSE 0 END)
        FROM read_parquet('{inventory_path}')
        """
    ).fetchone()
    assert row is not None
    per_year = connection.sql(
        f"""
        SELECT substr(filing_date, 1, 4) AS y, count(*)
        FROM read_parquet('{inventory_path}')
        WHERE eligibility_status != 'excluded' AND filing_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    return {
        "inventory_path": str(inventory_path),
        "inventory_rows": pq.read_metadata(inventory_path).num_rows,
        "denominator_accessions": row[0],
        "entities": row[1],
        "amendment_rate": round(float(row[2]), 4),
        "filings_per_year": {y: n for y, n in per_year},
    }


def generate_observations(profile: dict, out_dir: Path, seed: int = 42) -> Path:
    """Long canonical-observation table with inventory-derived skew."""
    rng = random.Random(seed)
    out = out_dir / "observations_raw.parquet"
    if out.exists():
        return out
    out_dir.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    entity_ids = [f"ent_{i:06d}" for i in range(int(profile["entities"]))]
    for year, filings in sorted(profile["filings_per_year"].items()):
        year_int = int(year)
        if year_int < 2010:
            continue
        rows = []
        for _ in range(int(filings)):
            entity = rng.choice(entity_ids)
            accession = (
                f"{rng.randrange(10**9):010d}-{year[2:]}-{rng.randrange(10**6):06d}"
            )
            available = f"{year}-{rng.randrange(1, 13):02d}-{rng.randrange(1, 29):02d}"
            period_end = f"{year_int - rng.randrange(0, 2)}-{rng.choice(['03-31', '06-30', '09-30', '12-31'])}"
            for metric in METRICS:
                rows.append(
                    {
                        "entity_id": entity,
                        "metric_id": metric,
                        "metric_group": METRIC_GROUPS[metric],
                        "fiscal_period_end": period_end,
                        "available_at": available,
                        "available_year": year_int,
                        "value": rng.normalvariate(0, 1) * 1e6,
                        "accession": accession,
                    }
                )
        table = pa.Table.from_pylist(rows)
        if writer is None:
            writer = pq.ParquetWriter(out, table.schema)
        writer.write_table(table)
    assert writer is not None
    writer.close()
    return out


def build_layout(
    raw: Path, out_dir: Path, name: str, sort: str, partition_by_group: bool
) -> Path:
    target = out_dir / name
    if target.exists():
        return target
    connection = duckdb.connect()
    partition = (
        "available_year, metric_group" if partition_by_group else "available_year"
    )
    connection.execute(
        f"""
        COPY (
          SELECT *,
            -- effective interval: closed by the next version of the same key
            lead(available_at) OVER (
              PARTITION BY entity_id, metric_id, fiscal_period_end
              ORDER BY available_at
            ) AS valid_to,
            available_at AS valid_from
          FROM read_parquet('{raw}')
          ORDER BY {sort}
        ) TO '{target}'
        (FORMAT PARQUET, PARTITION_BY ({partition}), ROW_GROUP_SIZE 122880)
        """
    )
    return target


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*.parquet"))


def run_queries(layout_dir: Path) -> dict:
    glob = f"{layout_dir}/**/*.parquet"
    queries = {
        "pit_as_of_cross_section": f"""
            SELECT entity_id, metric_id, value
            FROM read_parquet('{glob}', hive_partitioning=true)
            WHERE metric_id IN ('metric_01','metric_05','metric_09','metric_13','metric_17')
              AND valid_from <= '2018-06-30' AND (valid_to IS NULL OR valid_to > '2018-06-30')
              AND available_year <= 2018
        """,
        "metric_year_cross_section": f"""
            SELECT entity_id, value
            FROM read_parquet('{glob}', hive_partitioning=true)
            WHERE metric_id = 'metric_07' AND available_year = 2020
        """,
        "company_history_projection": f"""
            SELECT metric_id, fiscal_period_end, available_at, value
            FROM read_parquet('{glob}', hive_partitioning=true)
            WHERE entity_id = 'ent_000123'
            ORDER BY metric_id, available_at
        """,
    }
    results = {}
    connection = duckdb.connect()
    for name, sql in queries.items():
        timings = []
        rows = 0
        for _ in range(3):
            started = time.monotonic()
            rows = len(connection.sql(sql).fetchall())
            timings.append(time.monotonic() - started)
        results[name] = {
            "rows_returned": rows,
            "best_wall_seconds": round(min(timings), 3),
        }
    return results


def incremental_write_cost(raw: Path, layout_dir: Path, sort: str) -> dict:
    """Cost to append one new availability year to the layout."""
    connection = duckdb.connect()
    started = time.monotonic()
    connection.execute(
        f"""
        COPY (
          SELECT *, available_at AS valid_from, NULL AS valid_to
          FROM read_parquet('{raw}')
          WHERE available_year = 2025
          ORDER BY {sort}
        ) TO '{layout_dir}/_incremental_probe'
        (FORMAT PARQUET, ROW_GROUP_SIZE 122880)
        """
    )
    elapsed = time.monotonic() - started
    probe = Path(f"{layout_dir}/_incremental_probe")
    size = _dir_bytes(probe) if probe.is_dir() else probe.stat().st_size
    shutil.rmtree(probe, ignore_errors=True)
    return {"wall_seconds": round(elapsed, 2), "bytes_written": size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profile = cardinality_profile(args.inventory)
    raw = generate_observations(profile, args.out)
    raw_rows = pq.read_metadata(raw).num_rows

    candidates = {
        "year_pit_sort": ("pit_sort", False),
        "year_history_sort": ("history_sort", False),
        "year_group_pit_sort": ("pit_sort", True),
    }
    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cardinality_profile": profile,
        "synthetic_rows": raw_rows,
        "layouts": {},
    }
    for name, (sort_key, by_group) in candidates.items():
        layout = build_layout(raw, args.out, name, SORTS[sort_key], by_group)
        report["layouts"][name] = {
            "sort": SORTS[sort_key],
            "partitioning": "available_year, metric_group"
            if by_group
            else "available_year",
            "storage_bytes": _dir_bytes(layout),
            "queries": run_queries(layout),
            "incremental": incremental_write_cost(raw, layout, SORTS[sort_key]),
        }
    out_path = args.out / "report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out_path), "rows": raw_rows}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
