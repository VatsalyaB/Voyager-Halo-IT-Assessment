# TechSolve IT — Support Operations Analytics

Practical assessment for the **Data & AI Specialist** role. An end-to-end pipeline that
cleans a synthetic support-ticket export, combines it with NZ public-holiday data,
visualises it two ways (a web dashboard and a Power BI build), and exposes it through a
natural-language AI agent.

> The dataset is entirely synthetic (provided with the brief). No real customer data.

## The scenario
TechSolve IT (a fictional MSP) wants their operations manager to see *what* issues are
raised, *how* they're handled, and *where* to improve, from a 100,851-row ticket export.

## What's here
```
├─ README.md                     ← you are here
├─ requirements.txt              ← Python deps (pip install -r)
├─ data/
│  ├─ raw/         TechSolve - Ticket Data.xlsx      (source)
│  ├─ external/    NZ public holidays + business-day calendar (Nager.Date)
│  └─ processed/   fact_tickets.parquet/csv + star/ (Power BI-ready star schema)
├─ src/            clean_data.py · fetch_holidays.py · build_star_schema.py · build_dashboard_data.py
├─ dashboard_web/  self-contained ECharts dashboard (Part 2 — "or equivalent")
├─ powerbi/        BUILD_GUIDE.md + dax_measures.md + star-schema CSVs (Part 2 — Power BI)
├─ agent/          DuckDB + Claude/OpenAI + local-fallback NL agent (Part 3)
└─ docs/           DESIGN.md · DATA_QUALITY_REPORT.md · DECISION_LOG.md · REVIEW.md · screenshots/
```

## The three parts

### Part 1 — Source, combine & prepare  (`src/`, `data/`)
- Normalised **32 messy `category` variants → 10 canonical** categories + a 5-theme taxonomy.
- Removed corrupt-date rows, flagged impossible timelines, filled nulls with explicit sentinels.
- Joined **NZ public holidays incl. regional anniversary days** + a derived business-day calendar.
- Full transparency in [`docs/DATA_QUALITY_REPORT.md`](docs/DATA_QUALITY_REPORT.md).

### Part 2 — Visualise  (`dashboard_web/`, `powerbi/`)
- **Web dashboard** — self-contained HTML/ECharts, light/dark, 2024-2025 default + year filter,
  KPIs · issues · status/resolution · **holiday/business-day view** · team/region · **data-quality panel**
  · a **forecast & business-day capacity projection** (beyond the essentials — see below).
  Open `dashboard_web/index.html`. ([light](docs/screenshots/dashboard-light.png) · [dark](docs/screenshots/dashboard-dark.png))
- **Power BI** — model-ready star-schema CSVs + a complete step-by-step build guide
  (relationships, all 15 DAX measures, six pages): [`powerbi/BUILD_GUIDE.md`](powerbi/BUILD_GUIDE.md).

### Part 3 — AI agent  (`agent/`)
Ask the data questions in plain English. Claude/OpenAI translate to DuckDB SQL (read-only),
with a **deterministic local fallback** so it runs with no API key.
`streamlit run agent/app.py` or `python agent/cli.py "sla breach by team"`.
([demo](docs/screenshots/agent-demo.png))

## The headline finding
The export's `sla_breached` flag agrees with a recomputation (`resolution_time > sla_target`)
only **~50%** of the time — no better than chance — and 50 tickets are "resolved" before they
were created. Rather than hide it, the dashboard **reports the system-of-record field and
surfaces the gap** in a Data-Quality panel, with a recommendation to audit the source system.

## Beyond the essentials — forecast & capacity
The dashboard closes with a forward-looking section (`src/forecast.py`,
[`docs/FORECAST_METHODOLOGY.md`](docs/FORECAST_METHODOLOGY.md)). I tested the monthly series for
trend and seasonality, found **none** (slope ≈ 0, R² = 0.0007), so the volume forecast is a
**confident flat baseline** — and I flag that the unusually low variance is itself a synthetic-data
tell. The genuinely actionable piece is a **business-day capacity projection**: steady arrivals
(~183/day) ÷ staffed business days = the load each staffed day must clear per future quarter, with
public holidays compressing capacity. It demonstrates forecasting *and* the judgment to know when the
signal is weak.

## Reproduce end-to-end
```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
python src/fetch_holidays.py        # external data
python src/clean_data.py            # clean + join -> fact table + DQ report
python src/build_star_schema.py     # Power BI star schema
python src/build_dashboard_data.py  # web dashboard data (data.js/json)
python src/forecast.py              # forecast + capacity projection (forecast.js + methodology)
# then: open dashboard_web/index.html   ·   streamlit run agent/app.py
```

## Documentation (`docs/`)
- [`REVIEW.md`](docs/REVIEW.md) — the required written review (6 questions).
- [`INSIGHTS.md`](docs/INSIGHTS.md) — findings → recommendations brief for the ops manager.
- [`DATA_QUALITY_REPORT.md`](docs/DATA_QUALITY_REPORT.md) — every cleaning transformation, with counts.
- [`FORECAST_METHODOLOGY.md`](docs/FORECAST_METHODOLOGY.md) — forecast + capacity method.
- [`DECISION_LOG.md`](docs/DECISION_LOG.md) — every decision and why.
- [`DESIGN.md`](docs/DESIGN.md) · [`WALKTHROUGH.md`](docs/WALKTHROUGH.md) · [`INTERVIEW_PREP.md`](docs/INTERVIEW_PREP.md) · [`DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — plan, plain-English walkthrough, Q&A study sheet, demo storyboard.
- `screenshots/` — dashboard (light/dark), agent, and `demo.gif`.
