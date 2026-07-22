# Insights & Recommendations — for the Operations Manager

A one-page brief that turns the analysis into **decisions**. Each item is a finding, why it matters,
and what to do about it. (Numbers are reproducible from the pipeline; see `DATA_QUALITY_REPORT.md`.)

> **Executive summary.** Support demand is stable and predictable, so this is a *capacity-planning*
> problem, not a demand-volatility one — the lever is staffing steadily against a known rate, with
> extra cover around public holidays. But before trusting any performance number, **the SLA data needs
> auditing**: the system's breach flag disagrees with the underlying resolution times about half the
> time. Several signals also indicate this export is synthetic, so treat the *methods* as the
> deliverable and re-validate against a real extract before acting operationally.

---

### 1. Your SLA breach flag can't be trusted yet — audit it
- **Finding:** the provided `sla_breached` flag reports a **50.2%** breach rate, but recomputing breach
  from resolution time vs. the SLA target gives **91.7%** — and the two agree only **~50%** of the time
  (no better than a coin flip). 50 tickets are even marked resolved *before* they were created.
- **So what:** your headline SLA performance is effectively **unverified**. If SLA breaches drive
  customer credits, penalties, or team KPIs, the reported figure — and its financial exposure — could be
  materially wrong in either direction.
- **Recommendation:** reconcile the SLA calculation at source (does the flag use business hours? a
  different clock? a manual override?). Until it reconciles, report the system-of-record figure **with a
  data-quality caveat**, not as fact. *(The dashboard's Data-Quality panel shows the gap explicitly.)*

### 2. Support load is flat all week — staff seven days, not five
- **Finding:** ticket arrivals are roughly the same on **business days, weekends, and public holidays**
  (~150–184/day for each) — there is no weekday peak.
- **So what:** a weekday-heavy roster would build a weekend/holiday backlog that spills into Monday.
- **Recommendation:** move to **steady seven-day coverage** (or clear weekend/after-hours capacity)
  rather than a Monday–Friday model.

### 3. Demand is predictable — plan capacity, don't forecast surges
- **Finding:** monthly volume is stable (~5,600/month, ~183/day) with **no trend and no seasonality**
  (trend R² = 0.0007). Next quarters project to ~**16,700 arrivals** each.
- **So what:** this is a **capacity-planning** problem, not a demand-volatility one — you don't need a
  demand-forecasting model, you need the right baseline headcount.
- **Recommendation:** baseline-staff to the known rate, then adjust for **staffed business days**:
  **2025-Q2 is the tightest** — 5 public holidays leave ~60 staffed days for ~16,700 tickets
  (**~278/staffed-day**) vs. ~256/day in Q3. **Pre-plan holiday cover for Q2 and Q4.**

### 4. No single problem area dominates — balance, and watch for drift
- **Finding:** the 10 issue categories are almost evenly split (~10,000 tickets each across 5 themes).
- **So what:** there's no one hotspot to throw resources at; effort should be balanced across themes.
- **Recommendation:** in production, track category **share over time** and target whichever *grows* —
  the even split here is itself a sign of synthetic data (see §5), so don't read priorities into it.

### 5. Treat this dataset as synthetic — validate before acting
- **Finding:** three independent signals say the data is machine-generated, not a real export:
  measure fields are internally random (resolution time is uncorrelated with the timestamps), the
  free-text fields don't match their categories, and monthly volume is *statistically implausibly*
  flat for a real support queue.
- **So what:** conclusions drawn *from the values* won't transfer; the **approach** (cleaning rules,
  model, agent, capacity method) is what transfers.
- **Recommendation:** re-run this pipeline against a **real** ticket extract before making operational
  decisions; the code is built to do exactly that.

---

**Bottom line for the manager:** fix the SLA data, staff to a steady seven-day baseline with holiday
cover, and don't over-invest in demand forecasting — the demand is already predictable; the uncertainty
is in the *data quality*, not the *demand*.
