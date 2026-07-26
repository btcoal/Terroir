"""Regenerate config/taxonomy_vintages.json by probing published packages.

The vintage list is the UF-013 superset: every SEC/FASB-published standard
taxonomy package from the Release 1 filing start forward, enumerated from
the hosts themselves. Gaps the probe cannot resolve are recorded under
known_gaps so the UF-021 coverage check has an explicit target.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.config import load_config  # noqa: E402
from us_fundamentals.sec_transport import SecTransport  # noqa: E402

LIST_PATH = PROJECT_ROOT / "config" / "taxonomy_vintages.json"

PATTERNS = {
    "us-gaap": [
        "https://xbrl.fasb.org/us-gaap/{y}/us-gaap-{y}.zip",
        "https://xbrl.fasb.org/us-gaap/{y}/us-gaap-{y}-01-31.zip",
    ],
    "srt": [
        "https://xbrl.fasb.org/srt/{y}/srt-{y}.zip",
        "https://xbrl.fasb.org/srt/{y}/srt-{y}-01-31.zip",
    ],
    "dei": [
        "https://xbrl.sec.gov/dei/{y}/dei-{y}.zip",
        "https://xbrl.sec.gov/dei/{y}/dei-{y}-01-31.zip",
    ],
    "country": [
        "https://xbrl.sec.gov/country/{y}/country-{y}.zip",
        "https://xbrl.sec.gov/country/{y}/country-{y}-01-31.zip",
    ],
    "currency": [
        "https://xbrl.sec.gov/currency/{y}/currency-{y}.zip",
        "https://xbrl.sec.gov/currency/{y}/currency-{y}-01-31.zip",
    ],
    "exch": [
        "https://xbrl.sec.gov/exch/{y}/exch-{y}.zip",
        "https://xbrl.sec.gov/exch/{y}/exch-{y}-01-31.zip",
    ],
    "stpr": [
        "https://xbrl.sec.gov/stpr/{y}/stpr-{y}.zip",
        "https://xbrl.sec.gov/stpr/{y}/stpr-{y}-01-31.zip",
    ],
}

KNOWN_GAPS = [
    {
        "family": "us-gaap",
        "vintages": [2009, 2010],
        "reason": (
            "Pre-2011 us-gaap packages were hosted at taxonomies.xbrl.us, "
            "which no longer serves them. Early-vintage filings that "
            "reference them are rare (UF-010A: XBRL mandate phase-in) and "
            "their consumed schemas are captured per-accession as external "
            "closure objects under UF-012. Resolve via SEC archive mirror "
            "if the UF-021 coverage check reports live references."
        ),
    },
    {
        "family": "dei/country/currency/exch/stpr",
        "vintages": "non-annual",
        "reason": (
            "SEC document/entity and code-list families publish a vintage "
            "only in years the taxonomy changed; missing years are not "
            "gaps. Filings reference the most recent published vintage."
        ),
    },
]


def main() -> int:
    config = load_config()
    packages = []
    with SecTransport(config.sec, PROJECT_ROOT / ".spike" / "http_cache") as transport:
        for family, patterns in PATTERNS.items():
            for year in range(2009, 2027):
                for pattern in patterns:
                    url = pattern.format(y=year)
                    if transport.head(url) == 200:
                        packages.append({"family": family, "vintage": year, "url": url})
                        break
    payload = {
        "schema_version": 1,
        "list_version": "1.0.0",
        "coverage_start_year": 2009,
        "packages": sorted(packages, key=lambda p: (p["family"], p["vintage"])),
        "known_gaps": KNOWN_GAPS,
    }
    LIST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"{len(packages)} packages -> {LIST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
