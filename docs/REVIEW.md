# Review - Data & AI Specialist Practical

## 1. Where did your datasets come from, and why did you choose them?

**Primary:** the provided `TechSolve - Ticket Data.xlsx` - 100,851 rows, one per support ticket.

**External:** New Zealand public holidays for 2023–2025 from the **Nager.Date** public API
(`date.nager.at`), plus a **business-day calendar** I derived from it (each date tagged
business day / weekend / public holiday). I chose holidays over the other suggested options
(weather, etc.) for two reasons: the tickets carry an NZ `region` **and** a timestamp, so
holidays join on *both* place and time; and Nager.Date returns NZ **regional anniversary days**
(Auckland/Canterbury/Wellington Anniversary…), which join directly to the `region` column - an
NZ-specific angle a generic calendar can't provide. I considered weather but dropped it: noisier,
a weaker causal link to ticket volume, and a heavier per-region join for less analytical payoff.
The pipeline falls back to a hardcoded national-holiday list if the API is unreachable, so it's
reproducible offline.

## 2. Describe your process for working through this scenario.

1. **Profile first.** Before writing any transformation I profiled all 36 columns - types,
   null rates, cardinality, date ranges, and the distribution of every categorical. This
   surfaced the real problems early (see §4 findings) rather than discovering them mid-build.
2. **Clean & prepare (Part 1).** A reproducible `pandas` pipeline: normalise categories via an
   explicit synonym map, remove/flag date anomalies, apply per-column null rules, derive fields,
   and join the external calendar. It emits a **data-quality report** documenting every change.
3. **Model.** Built a star schema (fact + `dim_date` / `dim_customer` / `dim_category`) so both
   the Power BI model and the analytics are clean and reusable.
4. **Visualise (Part 2).** A self-contained web dashboard (built and verified in a real browser)
   plus a **built 6-page Power BI `.pbix`** (`powerbi/TechSolve Support Operations.pbix`) with a build guide documenting every DAX measure, so the story is told both ways. As a
   "beyond the essentials" addition I also built a caveated **volume forecast** and a **business-day
   capacity projection**.
5. **AI agent (Part 3).** A DuckDB query layer with a read-only safety gate, an LLM text-to-SQL
   layer, and a deterministic offline fallback.
6. **Document as I went** - a running decision log became the source for this review.

## 3. What tools and programs did you use, and why those over alternatives?

| Tool | Used for | Why over alternatives |
|---|---|---|
| **Python + pandas** | cleaning, transformation | Expressive, auditable, fully reproducible vs. point-and-click cleaning in Excel/Power Query (which is harder to review and re-run). |
| **pyarrow / Parquet** | the cleaned fact table | Compact and fast to reload across the dashboard and agent steps. |
| **Nager.Date API** | external holiday data | Free, no key, and returns regional anniversaries - see §1. |
| **DuckDB** | agent's query engine | In-process SQL directly over Parquet - no DB server to stand up; ideal for read-only analytical queries. |
| **ECharts (vendored)** | web dashboard | Rich, dependency-free once vendored; the file works offline and on GitHub Pages. |
| **Streamlit** | agent UI | Fastest way to a clean chat interface over Python. |
| **Power BI Desktop** | the "expected" dashboard | Directly matches the brief; I delivered a **built 6-page `.pbix`** on a star-schema model, plus a build guide, so it's reproducible. |
| **Claude (AI assistant)** | pair-programming throughout | See §6. |

I deliberately picked a **CVD-safe, accessibility-checked colour palette** for the dashboard and
validated it with a script rather than by eye.

## 4. What would you do differently? What did you find most challenging?

**Most challenging - and most interesting - was that the data is internally inconsistent.**
It's synthetic with several independently-randomised fields, so the usual assumptions break:

- `resolution_time_hours` has **~zero correlation** with `resolved − created`.
- `sla_breached` agrees with a recomputation (`resolution_time > sla_target`) only **~50%** of
  the time - a coin flip.
- **50 tickets are "resolved" before they were created**, and *every* ticket carries a resolved
  date regardless of status.
- The free-text `issue_description`/`resolution_notes` are randomly assigned and don't correspond
  to the category, so they're not usable for analysis.
- By created date the whole export is ~**67% 2024 / ~33% 2023** (2025 has just **10** rows); it's within the brief's default **2024–2025** view that 2024 is ~**99.98%** - despite the brief mentioning **2024–2025**.

The key judgement call was **how to report a metric whose source fields contradict each other**.
I chose to treat the ticketing system's provided fields as the *system of record* (that's what an
MSP is measured on), **prove** why recomputing from the timestamps is unsafe (they're broken), and
then make the discrepancy **visible** in a dedicated Data-Quality panel with a recommendation to
audit the source - rather than silently trusting one field or hiding the problem.

On the **date-window mismatch** I reached out to the hiring team (Anj) to confirm the intended
period, and in the meantime defaulted to 2024–2025 per the brief with an all-years filter. That
also prompted a nice judgement exercise: I considered whether "2024–2025" implied I should *forecast*
2025 from prior data, and concluded the brief is retrospective - but added a **forecast + capacity
projection** anyway as a value-add. Building it *was* the lesson: the series has no real trend or
seasonality (R² ≈ 0), so the honest output is a confident flat forecast plus an actionable
business-day capacity view, not a spurious growth curve - and the suspiciously low variance is itself
a synthetic-data tell.

**What I'd still do with more time:** surface SLA measured in *business hours* (using the holiday
calendar) as a headline rather than a secondary metric; and add automated tests around the cleaning
rules. I also ran an adversarial self-review of my own code that caught five real bugs (a security
hole in the agent's query gate, two dashboard miscalculations, a robustness crash, and a row-cap
bypass) - a reminder to verify the failure paths, not just the demo.

## 5. Roughly how long did you spend on each phase?

*(Approximate - AI assistance compressed the mechanical parts; the thinking time is mine.)*

| Phase | Approx. time |
|---|---|
| Profiling & understanding the data | ~1 hr |
| Part 1 - cleaning, external join, star schema, DQ report | ~2 hrs |
| Part 2 - web dashboard (build + browser-verify) | ~2 hrs |
| Part 2 - Power BI model + build guide | ~1 hr |
| Part 3 - AI agent (engine, fallback, UI) | ~2 hrs |
| Forecast & capacity value-add | ~1 hr |
| Documentation, self-review & fixes | ~1.5 hrs |
| **Total** | **~10.5 hrs** |

## 6. Did you use AI tools during this practical? If so, how?

Yes - transparently, and the brief explicitly invites it. I used **Claude (an AI coding
assistant)** as a pair-programmer throughout: to accelerate profiling, to draft and iterate on
the pandas pipeline and the dashboard/agent code, to generate the Power BI build guide and build
out the 6-page report from my star-schema spec, and to help write up documentation. I directed the work and made the analytical
judgement calls myself - in particular the data-quality findings in §4, the decision to treat the
provided SLA fields as system-of-record while surfacing the discrepancy, the choice of external
data source, and the taxonomy. Every number in the dashboards and the data-quality report is
produced by code in this repo and is fully reproducible from the raw file; I verified the
pipeline outputs and the dashboards rather than taking generated results on trust. Fittingly, the
practical itself includes an AI agent - so AI shows up both as a tool I used to build the solution
and as a component of the solution.
