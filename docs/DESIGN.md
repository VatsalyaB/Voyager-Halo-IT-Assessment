# TechSolve IT - Data & AI Specialist Practical: Design Spec

**Author:** Vatsalya Baranwal · **Date:** 2026-07-21 · **Due:** 2026-07-27
**Role:** Data & AI Specialist (Halo IT / Voyager)

This spec is the plan of record. It also seeds the required **Review** write-up
(`REVIEW.md`), which answers the six brief questions in the candidate's own voice.

---

## 1. Scenario & objective

TechSolve IT (fictional MSP) wants their operations manager to have visibility into
support performance: *what* issues are raised, *how* they're handled, and *where* to
improve. We are given a 100,851-row ticket export and must (1) clean & combine it with
an external source, (2) build a dashboard, (3) build an AI agent that answers NL
questions about the data, and (4) write a reflective review.

## 2. Dataset profile (as found)

- **Shape:** 100,851 rows × 36 columns, single sheet.
- **Grain:** one row per ticket (`ticket_id` unique). ~5,976 customers, 400 companies.
- **Geography:** NZ regions (Auckland 37%, Canterbury, Wellington, …) → enables an
  NZ-specific external join.

### 2.1 Data-quality findings (these drive the cleaning rules)

1. **`category` is dirty but recoverable - pure normalization.** 32 raw variants collapse
   to **10 canonical categories** via an explicit synonym map (casing/abbreviation/
   snake_case noise only, e.g. `BUG`/`Bug report`/`bug_report` → *Bug Report*). 0 unmapped.
2. **Free-text fields are randomized, not semantic.** Each of the 10 templated
   `issue_description` strings maps to *all 10* categories ~evenly (~10% each). So
   `issue_description`/`resolution_notes` **cannot** validate or repair `category`, and
   are unreliable for analysis. (Finding, not a fix.)
3. **Operational "measure" fields are mutually inconsistent (synthetic noise):**
   - `resolution_time_hours` (range 1–240h) has **~0 correlation** (r=0.0002) with
     `resolved − created`.
   - `sla_breached` agrees with recomputation (`resolution_time_hours > sla_target_hours`)
     only **50.2%** of the time - no better than chance.
   - **50 tickets** have `resolved_date < created_date` (impossible).
   - **Every** ticket has a `resolved_date`, including `Open`/`In Progress` - so the
     resolved timestamp is unreliable as a "was it resolved?" signal.
4. **Date range vs brief mismatch.** By `ticket_created_date`: 1970 ×5, **2023 ×33,676**,
   **2024 ×67,157**, 2025 ×10, 2099 ×3. The brief's "2024–2025" window is ~99.98% just
   2024; a strict filter silently drops all of 2023. → **Decision:** default the dashboard
   to 2024–2025 (per brief) with a year slicer exposing all years, and document the
   mismatch in the Review. *(Optional: raise as a clarifying question to Anj - draft in §8.)*
5. **Nulls (non-fabricated handling):** `account_manager` 66% → "Unassigned";
   `billing_contact_email` 56% → leave null; `industry`/`company_name` ~31% → "Unknown";
   `browser` 22% → "N/A (non-web channel)" where channel ≠ Web/Chat, else "Unknown";
   `team`/`assigned_to`/`csat_score` ~2% → "Unassigned"/null (excluded from CSAT averages).

### 2.2 Metric source-of-truth rules (declared, documented)

Because the measure fields don't reconcile, the reporting layer uses **explicit, stated
rules** rather than silently trusting any single column:

- **Created-date trends:** use `ticket_created_date` (raw event), after dropping the 8
  garbage-year rows (1970/2099).
- **Time to resolution & SLA:** use the provided operational fields
  (`resolution_time_hours`, `sla_target_hours`, `sla_breached`) as the **system-of-record**
  metrics (clean-ranged, complete, explicitly labeled). Time-to-resolution charts restrict
  to `status ∈ {Resolved, Closed}`.
- **Data-quality panel:** surface the reconciliation gaps (SLA flag vs recomputation 50%;
  50 negative durations) as an *insight* for the ops manager - "your SLA flag disagrees
  with your resolution times; audit the source system."
- **Business-hours SLA (derived, illustrative):** using the NZ holiday + business-day
  calendar, show how SLA compliance would look measured in business hours (excl. weekends
  & public holidays). Clearly labeled as a derived enhancement.

## 3. Category taxonomy (Part 1 - "categories and sub-categories")

Two-level hierarchy for reporting: **Theme → Category** (the 10 canonical values as
sub-categories).

| Theme                | Categories (sub-categories)                                   |
|----------------------|---------------------------------------------------------------|
| Access & Security    | Login Issue · Security Concern                                 |
| Billing & Payments   | Payment Problem · Refund Request                              |
| Account Lifecycle    | Account Suspension · Subscription Cancellation               |
| Product & Reliability| Bug Report · Performance Issue · Data Sync Issue             |
| Product Feedback     | Feature Request                                               |

## 4. External data source

- **NZ public holidays** (national + **regional anniversary days** - Auckland/Canterbury/
  Wellington/Otago Anniversary…), 2023–2025, via the Nager.Date API (fallback:
  data.govt.nz). Regional anniversaries join to the `region` column - a genuinely
  NZ-aware touch.
- **Derived business-day calendar:** flags each date as business day / weekend / holiday,
  enabling business-hours SLA and "tickets around holidays / long weekends" analysis.

## 5. Deliverables

### Part 1 - `src/` pipeline → `data/processed/` star schema
`clean_data.py` (normalize categories, apply taxonomy, integrity fixes, null rules,
derived fields), `fetch_holidays.py` (external source), `build_star_schema.py`
(fact_tickets + dim_date/dim_customer/dim_category/dim_team/dim_service_area). Emits a
**data-quality report** documenting every transformation (feeds the Review).

### Part 2 - dashboards (both)
- **Web** (`dashboard_web/index.html`, self-contained, GitHub-Pages ready; built & verified
  in-browser here). Pre-aggregated compact JSON so 100k rows stay fast. Sections:
  Overview KPIs · Ticket Issues (theme/category, service area) · Status · Time-to-Resolution
  & SLA · Holiday/business-day combined visual · Team & Regional · Data-Quality panel.
- **Power BI** (`powerbi/`): a **built 6-page `.pbix`** (10 DAX measures) on the star-schema model,
  plus model-ready CSVs + `BUILD_GUIDE.md` (relationships, DAX measures, page-by-page visual specs) as
  the reproducible spec.

### Part 3 - AI agent (`agent/`)
Streamlit chat over the cleaned data. **NL → SQL over DuckDB** (schema + few-shot in prompt),
read-only execution, natural-language answer. **API-agnostic** (Claude *or* OpenAI) with a
**deterministic local fallback** (intent parser → parameterized queries: trends, team
performance, category volumes, SLA, CSAT) so it runs with no API key. Ship app + a recorded
demo (GIF/screens).

### Review - `docs/REVIEW.md`
Answers the six brief questions, sourced from the running `DECISION_LOG.md`.

## 6. Tooling & rationale (seed for Review Q3)

Python 3.12 + pandas 3.0.3 (cleaning); DuckDB (agent SQL engine + fast local analytics);
Streamlit (agent UI); ECharts vendored locally (web dashboard); Power BI Desktop (assessor
deliverable). Rationale captured per choice in `DECISION_LOG.md`.

## 7. Build order

1. Part 1 pipeline + external source + star schema + data-quality report.
2. Web dashboard (build + browser-verify).
3. Power BI build guide + model CSVs.
4. AI agent (local fallback first, then API adapters) + demo recording.
5. README + Review + Decision Log finalize.

## 8. Non-goals (YAGNI)

No weather join (noisier, deprioritized); no live/streaming data; no ML forecasting unless
time permits; no cloud hosting of the agent (local run + recording suffices per brief).
