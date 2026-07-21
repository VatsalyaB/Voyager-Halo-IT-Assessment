# Decision Log

Running log of the choices made and *why*, captured as the work happens. This is the
raw material for `REVIEW.md` (the required write-up). Newest entries at the bottom.

---

### D1 — External source: NZ public holidays + business-day calendar (not weather)
**Why:** The tickets carry NZ `region` and dates, so holidays join on both time and place.
NZ has **regional anniversary days** (Auckland/Canterbury/Wellington…), which join to the
`region` column — a genuinely NZ-aware angle a generic calendar can't give. Weather was
considered but dropped: noisier, weaker causal link to ticket volume, heavier per-region
join for less analytical payoff. Source: Nager.Date API (free, no key, returns county-level
anniversaries). Fallback to a hardcoded national-holiday set if offline.

### D2 — Category cleaning is *normalisation*, not semantic repair
**Why:** 32 raw variants are pure casing/abbreviation/snake_case noise (`BUG`, `Bug report`,
`bug_report` → *Bug Report*) and collapse cleanly to **10** canonical categories via an
explicit synonym map (0 unmapped; 20,832 rows rewritten). I checked whether the templated
`issue_description` could *validate* the category — it can't: each of the 10 descriptions
maps to all 10 categories ~evenly, so the free-text fields are randomly assigned and unusable
for analysis. Documenting that is itself a finding.

### D3 — Two-level taxonomy: 5 themes → 10 categories
**Why:** The brief asks for "categories and sub-categories." A theme layer (Access & Security,
Billing & Payments, Account Lifecycle, Product & Reliability, Product Feedback) over the 10
canonical categories gives an ops manager a clean drill-down for reporting.

### D4 — Drop garbage-date rows; flag (don't drop) impossible durations
**Why:** 8 rows have created-years of 1970/2099 — clearly corrupt, removed (documented). 50
rows are "resolved before created" — the row is otherwise valid, so I keep it but null its
timestamp-derived duration and flag it, rather than discard data.

### D5 — System-of-record metrics + a Data-Quality panel (the key call)
**Why:** The measure fields don't reconcile: `resolution_time_hours` is uncorrelated (r≈0)
with `resolved − created`, and `sla_breached` matches a recomputation only 50% of the time.
I use the **provided** operational fields (`resolution_time_hours`, `sla_breached`) as the
reporting basis — they're the ticketing platform's system-of-record analog and are
clean-ranged/complete — and I do **not** recompute from the timestamps, which I proved are
broken (50 negative durations; every status carries a resolved date). Instead I surface the
gap in a Data-Quality panel and recommend the ops manager audit the source system. Showing
the contradiction is more valuable than hiding it behind a clean-looking KPI.

### D6 — Time-to-resolution only for Resolved/Closed tickets
**Why:** All tickets carry a `resolved_date` regardless of status, so an Open ticket's
"resolution" is meaningless. Duration metrics restrict to `status ∈ {Resolved, Closed}`
(40,217 tickets).

### D7 — Nulls filled with explicit sentinels, never fabricated
**Why:** `account_manager` (66%)→"Unassigned", `industry`/`company_name` (~31%)→"Unknown",
`browser` (22%)→"N/A (non-web channel)" for phone/email/social else "Unknown". PII
(`billing_contact_email`) and `csat_score` left null and excluded from stats. No imputed
"average" values that would invent signal.

### D8 — Reporting window: default 2024-2025, filter exposes all years
**Why:** The export is ~99.98% 2024 by created date (2023 has 33k rows, 2025 only 10). I honor
the brief's stated 2024-2025 window as the default view but add a year slicer exposing the full
history, and flag the mismatch in the Review (optional email to Anj drafted separately).

### D9 — Tooling
**Why:** Python + pandas for cleaning (expressive, auditable, reproducible); pyarrow/parquet for
a fast compact fact table; DuckDB as the agent's SQL engine and for quick analytics; the star
schema (fact + dim_date/dim_customer/dim_category) is emitted as CSVs for Power BI. Low-cardinality
attributes stay on the fact (Power BI slices them without a dim).

### D10 — Web dashboard: pre-aggregate to JSON, don't ship 100k rows
**Why:** The browser only needs aggregates. `build_dashboard_data.py` pre-computes every chart's
numbers **per (value × year)** into a 43 KB `data.js`, so the year filter recomputes rates client-side
for any year selection while the page still loads instantly. Emitted as `data.js` (a `<script src>`)
not just `data.json` so the file works via `file://` (fetch of local JSON is blocked; a script tag isn't).

### D11 — Vendored ECharts + CVD-validated palette
**Why:** ECharts is vendored locally so the dashboard is self-contained (works offline / on GitHub
Pages, no CDN). Colours come from the dataviz reference palette and were **validated with a script**
(colour-blind separation, contrast) rather than by eye; magnitude charts use a single hue (identity is
on the axis), small categorical sets ≤5, and status/priority use ordinal ramps.

### D12 — Data-Quality panel turns the mess into an insight
**Why:** Instead of hiding the SLA reconciliation gap, the dashboard shows provided-vs-recomputed
breach side by side plus agreement %, impossible-timeline count, and rows cleaned — an actionable
finding for the ops manager (audit the source system). Verified in a real browser (no JS errors,
light+dark, filter recompute).

### D13 — Power BI delivered as model + build guide (not a hand-built pbix)
**Why:** Authoring a `.pbix` programmatically is fragile; a complete, correct build guide + model-ready
CSVs is reliable and reproducible, and doubles as hands-on Power BI practice. The guide specifies every
relationship, all 15 DAX measures, and six pages mirroring the web dashboard. Caught and fixed two
data-type traps in review: `customer_id` is a string key (typing it numeric would break the customer
join) and `created_week` is a date.

### D14 — AI agent: API-agnostic with a read-only gate and offline fallback
**Why:** The agent must work regardless of which LLM key (if any) is available. Claude/OpenAI do
NL→SQL; a deterministic keyword router is the no-key fallback; **all** paths run through one safe
executor (SELECT-only, single statement, forbidden-keyword block, auto-LIMIT) so the agent can never
mutate data. It queries the cleaned Parquet, and I exposed the **cleaned** category (not the raw
variant column) after catching that in testing. Default model `claude-opus-4-8`, overridable via env.

### D15 — Adversarial self-review caught five bugs the happy path missed
**Why:** After building, I ran a structured adversarial review of the deliverables. My own
testing used the happy path (live API, well-formed queries, single-year checks) and missed edge
cases. The review confirmed and I fixed: (1) `fetch_holidays` crashed on the **offline fallback**
(empty regional map → `sort_values` KeyError); (2) the dashboard's **avg-tickets-per-day** divided
by a calendar-day denominator that included 2025's near-empty full year, halving the numbers —
now clipped to the data's actual date span (≈153/day, not ≈92); (3) the **SLA actual-avg** bar was
weighted by total tickets instead of resolved tickets — now uses the correctly pooled resolution
average; (4) **security:** the agent's read-only gate blocked mutations but not DuckDB's file-read
functions (`read_text`/`glob`/…) — a query could read local files; fixed by `SET
enable_external_access=false` after load plus a keyword block; (5) the **row cap** could be defeated
by a trailing SQL comment — fixed by wrapping queries in a capped subquery. Lesson worth keeping:
verify the failure paths, not just the demo.
