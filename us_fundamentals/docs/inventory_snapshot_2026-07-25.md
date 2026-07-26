# Accession inventory build record — 2026-07-25

Source snapshots: bulk `submissions.zip` (retrieved 2026-07-25) and 66
quarterly `form.idx` files (2010Q1–2026Q2), both under `data/bulk/`.

- Rows: **1,014,676** (10-K/10-Q/10-K/A/10-Q/A across all submission history)
- Inventory logical hash:
  `77c62401eff628a332f4c76cab9722ac4404ec6bd5480454e5abb1114e6de165`
- Eligibility: 517,559 excluded (pre-2010 filing start), 497,117
  indeterminate (awaiting issuer classification; forms and dates pass)
- Source conflicts retained: 9,074 rows
- XBRL cliff at scale: 2010 filings 35,230 `none` vs 3,771 `xbrl`;
  2011 filings 21,328 `none` vs 17,873 `xbrl`
- UF-013 coverage check: pass — only documented gaps
  (us-gaap 2008/2009/2010, see `config/taxonomy_vintages.json`)

Rebuild: `uv run python -m us_fundamentals.inventory --submissions-zip
data/bulk/submissions.zip --index-dir data/bulk/indexes --policy
config/release_1_issuer_universe.json --out
data/inventory/accession_inventory.parquet`
