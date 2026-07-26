## 1. What to MODIFY (Critical Architectural Adjustments)

### A. Tighter Availability Time Buffer Logic

* **Current Spec:** Defines availability as $\text{acceptance time} + 5\text{ minutes}$.
* **Modification:** Split the availability timestamp into two distinct concepts: `sec_acceptance_time` and `effective_trading_available_at`.
* **Why:** A filing accepted at **3:58 PM EST** has an availability time of **4:03 PM EST** under your current rule. Technically, this is post-market, but standard backtesting engines operating on daily resolution might apply this signal to *that day's* close ($t$), creating catastrophic look-ahead bias.
* **Rule:** Standardize an explicit market-session boundary:

Keep three distinct things: raw `acceptance_datetime`; an `available_at` information boundary (acceptance + dissemination buffer) that governs whether a fact can enter a snapshot at all; and an execution-lag policy that lives in the *research layer* as a parameter, not in Gold. Expose a conservative session-aware convenience column if you want to foot-gun-proof naive daily engines, but default it to next-session and make it timezone-aware.



### B. Shift Arelle from In-Process Dependency to Microservice / CLI Batch

* **Current Spec:** Implies integrating `Arelle` directly as a core Python dependency in the parsing worker pipeline.

Arelle is extremely robust for compliance validation, but it is notoriously memory-intensive, single-threaded, and prone to memory leaks when loading multi-gigabyte custom XML taxonomies repeatedly in long-running processes. Running it in-process will choke orchestrators like Dagster or Ray.

"Fully stateless per filing" overshoots: reloading the us-gaap 2023 taxonomy for every filing is a large, avoidable cost.

The robust pattern is a pool of worker processes *warmed per taxonomy version*, with a bounded lifetime — each worker recycles after N filings or a memory-budget trip to reclaim leaks. So: out-of-process and recyclable, yes; stateless, no — cache the standard taxonomy in the warm worker and partition work by taxonomy version so you amortize the load. This also dovetails with 2C.


### C. Formalize the LLM Output Schema Constraints

* **Current Spec:** Section 3 provides a great JSON schema for concept mapping.
* **Modification:** Add an explicit constraint forcing the coding agent to enforce **Pydantic / Structured Outputs (JSON Schema)** on all LLM API calls.
* **Why:** Without strict JSON Schema enforcement at the API level, models will occasionally drop required keys (`confidence`, `mapping_rule_id`), breaking upstream SQL writers.

---

## 2. What to ADD (Missing Production Realities)

### A. Handling of Discontinued Operations and Non-GAAP Reclassifications

* **What's Missing:** A policy on how to handle restatements caused purely by discontinued operations.
* **Why:** When a company divests a subsidiary, GAAP mandates that prior-period comparative Income Statements in subsequent filings must reclassify those earnings as "Income from Discontinued Operations."
* **Addition:** Define explicit canonical metrics for:
* `income_from_continuing_operations`
* `discontinued_operations`
* `net_income_total`


This ensures that when a company restates historical periods to remove divested revenues, your point-in-time logic does not interpret the lower historical revenue as an accounting error or standard restatement.

This is a real and under-appreciated mechanism: on a divestiture, GAAP forces prior-period comparatives to reclassify the divested unit's revenue and expenses into discontinued operations, so the comparative prior-year *revenue* in the next filing drops — not from error, not from a normal restatement, but from reclassification. Your temporal QC would otherwise flag it as a suspicious downward revision. Adding `income_from_continuing_operations`, `discontinued_operations`, and `net_income_total` is correct. Push it one step further: the reclassification means *revenue and every operating line become non-comparable through time across the divestiture* — the continuing-ops basis itself changes — which silently distorts revenue-growth, asset-growth, and margin signals, not just net income. So beyond the three metrics, set a period-level `basis_change` flag (reason: discontinued-ops reclassification) so growth-signal construction can span or reset the basis deliberately. The metrics catch the level; the flag catches the comparability break.

The gap this edit *leaves*: A large share of 10-K/A filings are Part III executive-comp amendments with zero primary-statement XBRL deltas; treating every `/A` as a restatement event pollutes your revision-magnitude distributions. Discontinued-ops reclassification and non-financial amendments are the two "looks like a restatement but isn't" cases, and 2B only closes one. Add amendment-scope typing alongside it.

### B. Cold-Storage Strategy for Taxonomy Linkbases

* **What's Missing:** A caching and resolution architecture for external SEC/FASB standard schemas.
* **Why:** Parsing XBRL requires downloading target taxonomy schemas (e.g., `[http://fasb.org/us-gaap/2023/](http://fasb.org/us-gaap/2023/)...`). SEC EDGAR throttles requests aggressively (10 req/sec). If your parser fetches missing standard schemas dynamically during a 15-year historical backfill, you will be rate-limited instantly.
* **Addition:** Require a pre-populated "Taxonomy Cache" containing all US-GAAP, DEI, and SEC taxonomies from 2010 to present stored locally in the Bronze layer.

### C. Specific Integration Strategy for Market Identifiers (CIK-to-CRSP/Compustat Linking)

* **What's Missing:** A concrete pipeline for mapping CIK to CUSIP/FIGI over time.
* **Why:** As noted in Section 6.1, mapping CIKs to market price data is brutal because CIKs represent the legal parent, while tickers/CUSIPs represent issued securities.
* **Addition:** Add a mandatory sub-pipeline in Phase 4 that parses **Form 10-K/Q Cover Pages (Inline XBRL)**. Since ~2019, the SEC mandates cover-page tags for:
* `TradingSymbol`
* `SecurityTitle`
* `SecurityExchangeName`

One completeness note: it's not just us-gaap and dei — you need `srt` (2018+), `country`, `currency`, `exch`, `stpr`, and the role/reference schemas. Load them as offline Taxonomy Packages rather than URL resolution. Filer *extension* taxonomies don't belong in this cache — they arrive inside each filing package you're already downloading.

This provides an authoritative, unambiguous point-in-time history of a CIK's active tickers and exchanges directly from the primary SEC text.

NB: The dei cover-page tags give an authoritative PIT ticker/exchange history from the primary source — this is the SEC-native spine, exactly right for keeping the distributed artifact clean. Two caveats the edit misses. It starts ~mid-2019 (cover-page tagging mandate), so it does nothing for 2010–2019 ticker history — that gap still needs the SEC company-ticker file snapshots, filing headers, and your FirstRate `changed`-ticker logs. And a single CIK routinely carries *multiple* `TradingSymbol`/`Security12bTitle` tags (multiple listed classes), so model it one-CIK-to-many-symbols, not one ticker per filer.

---

## 3. What to REMOVE (Simplifications for Realizability)

### A. Remove Deep Unstructured Text / Footnote Parsing for Release 1.0

* **Current Spec:** Section 4.3 mentions parsing the Financial Statement and Notes Data Sets to capture segment data, lease disclosures, and debt maturity schedules in the initial rollout.
* **Recommendation:** **Remove Footnote Parsing from Phase 1.**
* **Why:** Footnote XBRL tagging (block tagging vs. detail tagging) is notoriously inconsistent across filers prior to recent years. Parsing lease schedules and debt maturity matrices from XBRL tables adds exponential complexity. Restrict Release 1.0 strictly to **Primary Financial Statements** (Balance Sheet, Income Statement, Cash Flow Statement, Cover Page).

## Summary of Actionable Specification Updates

If you hand this to an advanced coding agent, update **Phase 0 & Phase 1** to include these explicit directives:

1. **Storage Layer:** Force DuckDB/Parquet Partition by period (fiscal or filing year) for pruning, and make PIT queries fast the way they're actually bound — sort/cluster within partition by `(entity_id, metric_id, available_at)` so the version-resolution range scan on `available_at ≤ t` and DuckDB's zone maps do the work. Fiscal-year pruning alone doesn't accelerate the as-of resolution, which is the expensive part; metric is a column, let column pruning handle it. 

2. **Deterministic Guardrails:** Force the agent to write a **Metamorphic Test Suite** (as outlined in Section 12.7) *before* it builds the Gold-layer transformation queries. This ensures that any logic introduced later that violates point-in-time isolation fails CI immediately.

**The plan builds half the instrument.** The stated objective (line 18) is "compatibility with market-price and returns datasets," but the security master stops at CIK→security→listing and there's no returns/price side. For your actual use — a fund — the fundamentals are inert without clean linkage to a survivorship-free returns series, and *that* is arguably the harder problem than the fundamentals extraction you've specced so carefully. Add a section that explicitly declares it out of scope with a named interface, rather than leaving "compatibility" as an aspiration.

**A material omission in the core-50:** preferred equity (and preferred dividends) is in the section-7 ontology but missing from the section-17 recommended list. You can't compute `book_equity` correctly for financials-adjacent or preferred-heavy names, or clean ROE/earnings-yield, without subtracting preferred and getting net-income-to-common right. `net_income_common` is in the list but the preferred stock line that reconciles it isn't. Add `preferred_equity` and `preferred_dividends` to the fifty. I'd also reconsider that the fifty omits any redeemable/temporary equity (mezzanine) line, which your Assets = Liabilities + Equity check (616) already acknowledges you need to handle — the identity references it but the metric list doesn't carry it.

**Amendment scope needs typing.** Section 10 treats the version chain well, but a large fraction of 10-K/A filings contain no financial-statement changes at all — they're Part III executive-compensation amendments filed when the proxy is late, with no XBRL financial deltas. Treating every `/A` as a restatement event will over-generate restatement flags and pollute your revision-magnitude distributions (692). Add an amendment-classification step: does the amendment carry primary-statement XBRL deltas, and if so which statements, versus is it a non-financial amendment. This is a real and common failure mode, not an edge case.

**A few modifications rather than additions:**

The "store every downloaded byte immutably" principle (125) plus storing the "complete submission text file" for every accession (123) is a genuine cost you haven't budgeted — full submission packages across all domestic filers 2010+ run to multiple terabytes, most of it exhibits irrelevant to fundamentals. The immutability principle is right; "every byte" is the expensive part. Consider storing the XBRL-relevant documents plus the filing index and a manifest of hashes over the *full* package, with the full package re-fetchable on demand from EDGAR (which retains it). You keep verifiable provenance and reproducibility without paying to warehouse every 8-K exhibit.

Soften the "byte-equivalent" reproducibility claim (173). With Parquet compression metadata, file timestamps, and any Arelle/taxonomy drift, byte-equivalence is fragile; *logical* equivalence under a pinned manifest is the real, testable guarantee and you already state it as the alternative. Lead with logical equivalence and drop the byte claim, or you'll write a release gate (line 971) you can't actually pass.

Add a note that XBRL quality is strongly time-varying: the 2009–2012 vintage has materially higher custom-tag rates and tagging-error density (phase-in years). Your 2010/2011 start is reasonable, but the early years should carry heavier review weight or a later effective-start for the most error-prone metrics, and your precision-by-taxonomy-year reporting (768) will surface this — I'd make it an explicit expectation rather than a discovery.

Smaller notes: the `precision` field in raw_fact (260) is effectively vestigial — XBRL 2.1 allows `decimals` or `precision` but real filings almost universally use `decimals`; keep the column, expect it null. Your PIT availability policy (242) implicitly needs a trading-calendar dependency (holidays, half-days) for the "following trading session" rule — worth naming since it's a small but real correctness surface. And a currency/FX policy line is missing: even in a US-GAAP domestic universe you'll hit occasional non-USD reporting facts, and the `currency` column has no stated handling rule.