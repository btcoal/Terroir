"""UF-010A acquisition spike. THROWAWAY reference implementation.

Happy path only: select 50-100 accessions across vintages/forms/sizes, fetch
each parser-input closure through the production SecTransport, parse once
with Arelle, measure everything, write a report. No checkpointing, no
retries beyond the transport's own, no promotion of downloaded bytes.

Run:  uv run python scripts/spike_uf010a.py [--limit N]
Outputs: .spike/measurements.jsonl, .spike/report.md
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.config import load_config  # noqa: E402
from us_fundamentals.obslog import (  # noqa: E402
    component_logger,
    configure_logging,
    new_run_id,
)
from us_fundamentals.sec_transport import SecTransport  # noqa: E402

SPIKE_DIR = PROJECT_ROOT / ".spike"
QUARTERS = [
    "2010/QTR1",
    "2013/QTR2",
    "2016/QTR3",
    "2019/QTR4",
    "2022/QTR2",
    "2025/QTR3",
]
LARGE_FILER_QUARTER = "2023/QTR4"  # Apple's FY2023 10-K lands here
FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}
PER_QUARTER = 11
SEED = 20260725

NON_INSTANCE_XML = re.compile(
    r"(_cal|_def|_lab|_pre)\.xml$|^FilingSummary\.xml$|^R\d+\.xml$|-index|MetaLinks",
    re.IGNORECASE,
)

PARSE_SNIPPET = r"""
import json, resource, sys, time
from arelle import Cntlr

target, user_agent = sys.argv[1], sys.argv[2]
cntlr = Cntlr.Cntlr(logFileName="logToStdErr")
cntlr.webCache.httpUserAgent = user_agent
start = time.monotonic()
model = cntlr.modelManager.load(target)
elapsed = time.monotonic() - start
facts = len(getattr(model, "facts", []) or [])
errors = len([m for m in getattr(model, "errors", [])])
model.close()
print(json.dumps({
    "parse_seconds": round(elapsed, 2),
    "fact_count": facts,
    "error_count": errors,
    "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
}))
"""


def parse_form_idx(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        parts = line.split()
        # Parse from the right: company names may contain runs of spaces,
        # but form (no spaces for our set), CIK, date, and path are stable.
        if len(parts) >= 5 and parts[0] in FORMS and parts[-1].endswith(".txt"):
            try:
                cik = int(parts[-3])
            except ValueError:
                continue
            rows.append(
                {
                    "form": parts[0],
                    "company": " ".join(parts[1:-3]),
                    "cik": cik,
                    "filed": parts[-2],
                    "path": parts[-1],
                }
            )
    return rows


def accession_from_path(path: str) -> str:
    return Path(path).stem


def select_accessions(client: SecTransport, limit: int) -> tuple[list[dict], dict]:
    rng = random.Random(SEED)
    selected: list[dict] = []
    eligible_per_quarter: dict[str, int] = {}
    for quarter in QUARTERS:
        idx = client.get(
            f"https://www.sec.gov/Archives/edgar/full-index/{quarter}/form.idx"
        )
        rows = parse_form_idx(idx.content.decode("latin-1"))
        eligible_per_quarter[quarter] = len(rows)
        amendments = [r for r in rows if r["form"].endswith("/A")]
        plain = [r for r in rows if not r["form"].endswith("/A")]
        picks = rng.sample(plain, min(PER_QUARTER - 1, len(plain)))
        if amendments:
            picks.append(rng.choice(amendments))
        for row in picks:
            row["quarter"] = quarter
        selected.extend(picks)
    # Guarantee one heavy large-accelerated filer.
    idx = client.get(
        f"https://www.sec.gov/Archives/edgar/full-index/{LARGE_FILER_QUARTER}/form.idx"
    )
    rows = parse_form_idx(idx.content.decode("latin-1"))
    apple = [r for r in rows if r["cik"] == 320193 and r["form"] == "10-K"]
    if apple:
        apple[0]["quarter"] = LARGE_FILER_QUARTER
        selected.append(apple[0])
    return selected[:limit], eligible_per_quarter


def acquire_closure(client: SecTransport, row: dict, dest: Path) -> dict:
    accession = accession_from_path(row["path"])
    nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{row['cik']}/{nodash}"
    listing = json.loads(client.get(f"{base}/index.json").content)
    names = [item["name"] for item in listing["directory"]["item"]]

    wanted: list[str] = []
    instance_candidates: list[str] = []
    inline_instance = None
    for name in names:
        lower = name.lower()
        if lower.endswith(".xsd") or re.search(r"(_cal|_def|_lab|_pre)\.xml$", lower):
            wanted.append(name)
        elif lower.endswith("_htm.xml"):
            inline_instance = name
            wanted.append(name)
        elif lower.endswith(".xml") and not NON_INSTANCE_XML.search(name):
            instance_candidates.append(name)
            wanted.append(name)

    if inline_instance:
        primary = inline_instance[: -len("_htm.xml")] + ".htm"
        if primary in names:
            wanted.append(primary)
        parse_target = primary if primary in names else inline_instance
    else:
        parse_target = instance_candidates[0] if instance_candidates else None

    dest.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    stored = 0
    for name in dict.fromkeys(wanted):
        result = client.get(f"{base}/{name}")
        (dest / name).write_bytes(result.content)
        total_bytes += len(result.content)
        stored += 1

    return {
        "accession": accession,
        "cik": row["cik"],
        "company": row["company"],
        "form": row["form"],
        "quarter": row["quarter"],
        "filed": row["filed"],
        "object_count": stored,
        "closure_bytes": total_bytes,
        "parse_target": str(dest / parse_target) if parse_target else None,
        "inline": inline_instance is not None,
    }


def cold_parse(target: str, user_agent: str) -> dict | None:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", PARSE_SNIPPET, target, user_agent],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def cache_file_count(cache_dir: Path) -> int:
    return (
        sum(1 for p in cache_dir.rglob("*") if p.is_file()) if cache_dir.exists() else 0
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=68)
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    run_id = new_run_id()
    logger = component_logger("spike_uf010a", run_id, "spike")
    SPIKE_DIR.mkdir(exist_ok=True)
    measurements = SPIKE_DIR / "measurements.jsonl"

    arelle_cache = Path.home() / ".config" / "arelle" / "cache"
    cache_before = cache_file_count(arelle_cache)
    started = time.monotonic()

    with SecTransport(config.sec, SPIKE_DIR / "http_cache", logger=logger) as client:
        selected, eligible_per_quarter = select_accessions(client, args.limit)
        logger.info("selected", extra={"count": len(selected)})

        records = []
        with open(measurements, "w", encoding="utf-8") as sink:
            for i, row in enumerate(selected):
                accession = accession_from_path(row["path"])
                try:
                    record = acquire_closure(
                        client, row, SPIKE_DIR / "closures" / accession
                    )
                except Exception as error:  # happy-path spike: record and skip
                    logger.info(
                        "closure_failed",
                        extra={"accession": accession, "error": str(error)[:200]},
                    )
                    continue
                if record["parse_target"]:
                    parse = cold_parse(record["parse_target"], config.sec.user_agent)
                    record["cold_parse"] = parse
                records.append(record)
                sink.write(json.dumps(record) + "\n")
                sink.flush()
                logger.info(
                    "accession_done",
                    extra={
                        "accession": accession,
                        "n": i + 1,
                        "of": len(selected),
                        "objects": record["object_count"],
                        "bytes": record["closure_bytes"],
                        "parsed": bool(record.get("cold_parse")),
                    },
                )

    acquisition_seconds = round(time.monotonic() - started, 1)
    cache_after = cache_file_count(arelle_cache)

    summary = {
        "run_id": run_id,
        "selected": len(selected),
        "acquired": len(records),
        "parsed": sum(1 for r in records if r.get("cold_parse")),
        "eligible_per_quarter": eligible_per_quarter,
        "taxonomy_cache_files_before": cache_before,
        "taxonomy_cache_files_after": cache_after,
        "total_wall_seconds": acquisition_seconds,
        "forms": dict(Counter(r["form"] for r in records)),
    }
    (SPIKE_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
