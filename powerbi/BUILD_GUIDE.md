# Build Guide — TechSolve Support Operations (Power BI Desktop)

A step-by-step guide to build the `TechSolve Support Operations.pbix` report
from the four cleaned star-schema CSVs. Follow it top to bottom in **Power BI
Desktop**. DAX for every measure lives in the companion file
[`dax_measures.md`](./dax_measures.md).

The report mirrors the companion web dashboard, so both tell the same story:
Overview → Ticket Issues → Status & Time to Resolution → External Data → Team &
Region → Data Quality.

---

## 1. Prerequisites

- **Power BI Desktop**, already installed at
  `C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe`.
  Launch it from the Start menu or that path.
- The **four CSV files** in `data/processed/star/` (paths relative to the
  project root):
  - `fact_tickets.csv` — 100,843 rows (the fact table)
  - `dim_customer.csv` — 5,976 rows
  - `dim_category.csv` — 10 rows
  - `dim_date.csv` — 627 rows
- Roughly 5 minutes of import time on the fact table; it has ~100k rows and ~40
  columns.

> Tip: keep this repo's folder path handy — you'll point Get Data at
> `data/processed/star/`.

---

## 2. Import the data (Get Data → Text/CSV)

You can import the four files one at a time (clearest) or point at the folder.

### Option A — one file at a time (recommended)

For **each** of the four CSVs:

1. **Home** ▸ **Get data** ▸ **Text/CSV**.
2. Browse to `data/processed/star/` and select the file → **Open**.
3. In the preview dialog, set **Delimiter = Comma** and leave *Data Type
   Detection* on "Based on first 200 rows" (you'll fix types explicitly next).
4. Click **Transform Data** (not *Load*) to open **Power Query Editor**.

### Option B — Folder import

**Get data** ▸ **Folder** → select `star/` → **Combine & Transform**. This works
but each file has a different schema, so Option A keeps the four queries clean
and separate. Prefer Option A unless you're comfortable with folder combine.

### 2a. Set correct data types in Power Query

Do this per query (click the query in the left pane). Set types by clicking the
type icon in each column header, or select the column ▸ **Transform** ▸ **Data
Type**. Getting these right now prevents broken relationships and measures later.

**Dates** — set to type **Date**:

- `fact_tickets[created_date]`, `fact_tickets[resolved_date]`, `fact_tickets[created_week]`
- `dim_date[date]`
- `dim_customer[account_created_date]`

**Boolean columns** — these come from pandas as the **text** `"True"`/`"False"`.
Confirm Power BI typed them as **True/False (Boolean)**; if any imported as
**Text**, set the type to **True/False** now. On `fact_tickets`:

- `met_sla`, `sla_breached_provided`, `sla_breached_recomputed`,
  `sla_flags_agree`, `escalated_flag`, `is_genuinely_resolved`,
  `resolved_before_created`, `created_is_weekend`, `created_is_holiday`,
  `created_is_business_day`, `created_on_regional_anniversary`

On `dim_date`: `is_weekend`, `is_national_holiday`, `is_business_day`.

> If Power Query refuses to convert `"True"`/`"False"` text directly to
> True/False, first **Transform ▸ Format ▸ lowercase** on the column, then change
> the type to True/False. Alternatively, leave them as Text and use `= "True"`
> in the DAX (see the note in `dax_measures.md`). Pick one approach and be
> consistent.

**Numbers**:

- **Decimal number** — `resolution_time_hours`, `first_response_time_hours`,
  `sla_target_hours`, `resolution_hours_calc`, `business_days_to_resolve`,
  `csat_score`, `issue_complexity_score`, `monthly_contract_value` (on both
  `fact_tickets` and `dim_customer`).
- **Whole number** — `ticket_id`, `previous_tickets`, and on `dim_date`: `year`,
  `quarter`, `month`, `week`, `day_of_week`; `dim_customer[customer_tenure_months]`.
- **Text** — **`customer_id` on BOTH `fact_tickets` and `dim_customer`** (it's the
  relationship key and its values are strings like `ACC-07512` — if Power BI
  auto-typed it as a number, force it back to Text or the customer relationship
  will silently fail), plus the remaining descriptive columns (`category`, `theme`,
  `service_area`, `priority`, `status`, `team`, `assigned_to`, `channel`,
  `region`, `day_type`, `customer_name`, `company_name`, month/day names, etc.).

### 2b. Close & Apply

**Home** ▸ **Close & Apply**. Power BI loads all four tables. Wait for the fact
table (~100k rows) to finish.

---

## 3. Model relationships (Model view)

Switch to **Model view** (left rail, third icon). Create relationships by
dragging the key from the dimension to the matching column on `fact_tickets`, or
via **Home** ▸ **Manage relationships** ▸ **New**. Build these three **active**
relationships (each is one-to-many, single cross-filter direction, from the
dimension "one" side to the fact "many" side):

| From (one) | To (many) | Cardinality | Cross-filter | Active |
|---|---|---|---|---|
| `dim_date[date]` | `fact_tickets[created_date]` | 1 → * | Single | Yes |
| `dim_customer[customer_id]` | `fact_tickets[customer_id]` | 1 → * | Single | Yes |
| `dim_category[category]` | `fact_tickets[category]` | 1 → * | Single | Yes |

For each: confirm the arrow points **from the dimension to the fact**, cardinality
reads **One to many (1:*)**, and **Cross-filter direction = Single**. Leave
"Make this relationship active" checked.

### 3a. Mark `dim_date` as the date table

Select `dim_date` in the field list → **Table tools** ▸ **Mark as date table** →
choose the **`date`** column → **OK**. Power BI validates the column is a
contiguous, unique, gap-free set of dates.

**Why this matters:** marking a dedicated date table (a) makes time-intelligence
functions and the built-in date hierarchy behave correctly, (b) lets you slice
every fact by real calendar attributes (year, quarter, month name, week,
weekend/holiday flags) that live on `dim_date` rather than the auto-generated
hidden date tables Power BI would otherwise create per date column, and (c)
guarantees a continuous axis so months with zero tickets still appear on trend
lines. Always disable *auto date/time* for this model:
**File ▸ Options and settings ▸ Options ▸ Current File ▸ Data Load ▸ uncheck
Auto date/time**.

### 3b. Optional / advanced — inactive relationship on `resolved_date`

If you later want to analyze tickets by **resolution** date (e.g. "resolved per
month") rather than creation date, add a second relationship:

- `dim_date[date]` → `fact_tickets[resolved_date]`, 1 → *, **inactive** (Power BI
  only allows one active relationship between two tables).

Activate it inside a measure with `USERELATIONSHIP`, e.g.:

```dax
Resolved in Period =
CALCULATE (
    [Resolved Tickets],
    USERELATIONSHIP ( dim_date[date], fact_tickets[resolved_date] )
)
```

This is optional — the core report is built on the active `created_date`
relationship. Skip it if you're keeping the build lean.

---

## 4. Measures

Create one home for all measures so they're easy to find.

1. **Home** ▸ **Enter data** → leave the single default column, name the table
   **`_Measures`** → **Load**. (This creates an empty table; the placeholder
   column can be hidden.)
2. Select `_Measures` → **Table tools** ▸ **New measure**.
3. Open [`dax_measures.md`](./dax_measures.md) and paste each measure's
   `Name = expression` block, one at a time, pressing **Enter** after each.
4. Set each measure's format via **Measure tools** ▸ **Format** (percentages,
   decimals) per the checklist in `dax_measures.md`.

Alternatively, put the measures directly on `fact_tickets` — functionally
identical, just less tidy. The `_Measures` table keeps the field list clean.

**Measures to create (15):** Total Tickets · Resolved Tickets · Resolution Rate
· Avg Resolution Hours · Avg First Response Hours · SLA Breach Rate · SLA Breach
Rate (Recomputed) · SLA Flag Agreement · Avg CSAT · Escalation Rate · Avg
Business Days to Resolve · Resolved Before Created · Tickets on Public Holiday ·
Tickets on Regional Anniversary · Avg Tickets per Day.

### 4a. Calculated column — Resolution Band

The Status & Time page needs a resolution-time band. Add it as a **calculated
column** on `fact_tickets` (**Table tools** ▸ **New column**):

```dax
Resolution Band =
SWITCH (
    TRUE (),
    fact_tickets[resolution_time_hours] <= 4, "0-4h",
    fact_tickets[resolution_time_hours] <= 8, "4-8h",
    fact_tickets[resolution_time_hours] <= 24, "8-24h",
    fact_tickets[resolution_time_hours] <= 48, "24-48h",
    "48h+"
)
```

By default Power BI sorts these labels alphabetically (`0-4h`, `24-48h`, `4-8h`,
`48h+`, `8-24h`) — wrong order. Fix it with a companion **sort column**:

```dax
Resolution Band Sort =
SWITCH (
    TRUE (),
    fact_tickets[resolution_time_hours] <= 4, 1,
    fact_tickets[resolution_time_hours] <= 8, 2,
    fact_tickets[resolution_time_hours] <= 24, 3,
    fact_tickets[resolution_time_hours] <= 48, 4,
    5
)
```

Then select the **`Resolution Band`** column → **Column tools** ▸ **Sort by
column** ▸ **`Resolution Band Sort`**. The bands now render in ascending time
order on any visual.

---

## 5. Report pages

Build six pages (rename tabs at the bottom by double-clicking). For each visual:
click the visual type in the **Visualizations** pane, then drag fields onto the
named wells. All measures below come from `_Measures`; all descriptive/axis
fields come from the tables named.

### Page 1 — Overview

**KPI cards (6).** Use the **Card** visual, one measure each. Arrange in a row or
2×3 grid at the top:

1. **Total Tickets** — Total Tickets
2. **Resolution Rate** — Resolution Rate (shows as %)
3. **Avg Resolution Hours** — Avg Resolution Hours (1 decimal)
4. **SLA Breach Rate** — SLA Breach Rate (%)
5. **Avg CSAT** — Avg CSAT
6. **Escalation Rate** — Escalation Rate (%)

Give each card a short title matching the label above; set the callout value
decimals in **Format ▸ Callout value**.

**Line chart — tickets over time.**
- Visual: **Line chart**
- **X-axis:** `dim_date[month_name]` (or use the `dim_date` date hierarchy; for a
  continuous daily line use `dim_date[date]`)
- **Y-axis (Values):** Total Tickets
- Format: enable data labels off for density; if using `month_name`, set its
  **Sort by column** to `dim_date[month]` so months order Jan→Dec.
- **Optional forward view:** with the line chart selected (use a continuous
  `dim_date[date]`/month axis), open the **Analytics** pane (magnifying-glass icon) →
  **Forecast** → *Add* to overlay Power BI's built-in forecast with a confidence band.
  As the web dashboard notes, this series has no real trend or seasonality, so the
  forecast is essentially flat — the actionable forward view is the business-day
  **capacity projection** in `docs/FORECAST_METHODOLOGY.md`, not a growth curve.

**Donut chart — tickets by theme.**
- Visual: **Donut chart**
- **Legend:** `fact_tickets[theme]` (or `dim_category[theme]`)
- **Values:** Total Tickets
- Format: show category + percentage in detail labels.

**Year slicer.**
- Visual: **Slicer**
- **Field:** `dim_date[year]`
- Style as a list or dropdown. **Default selection:** click both **2024** and
  **2025** so the report opens focused on the two full years. (Ctrl-click to
  multi-select; this selection is saved with the file.)

### Page 2 — Ticket Issues

**Clustered bar — Total Tickets by category (sorted desc).**
- Visual: **Clustered bar chart**
- **Y-axis:** `fact_tickets[category]` (or `dim_category[category]`)
- **X-axis (Values):** Total Tickets
- Use the visual's **⋯ ▸ Sort axis ▸ Total Tickets ▸ Descending**.

**Bar — Total Tickets by service_area.**
- Visual: **Clustered bar chart**
- **Y-axis:** `fact_tickets[service_area]`
- **X-axis (Values):** Total Tickets · sort descending.

**Matrix — theme → category.**
- Visual: **Matrix**
- **Rows:** `theme`, then `category` (nested — gives a theme→category drilldown)
- **Values:** Total Tickets, SLA Breach Rate
- Format: turn on **Row subtotals** at the theme level; conditional-format the
  SLA Breach Rate column (background colour scale) to spotlight problem areas.

### Page 3 — Status & Time to Resolution

**Column — Total Tickets by status.**
- Visual: **Clustered column chart**
- **X-axis:** `fact_tickets[status]`
- **Y-axis (Values):** Total Tickets.

**Column — Total Tickets by Resolution Band.**
- Visual: **Clustered column chart**
- **X-axis:** `fact_tickets[Resolution Band]` (already sorted by
  `Resolution Band Sort` from step 4a)
- **Y-axis (Values):** Total Tickets.

**Clustered column — SLA target vs actual by priority.**
- Visual: **Clustered column chart**
- **X-axis:** `fact_tickets[priority]`
- **Y-axis (Values):** two series — **Average of `sla_target_hours`** and
  **Avg Resolution Hours**. (Drag `sla_target_hours` into Values and set its
  aggregation to **Average** via the field's dropdown; add the Avg Resolution
  Hours measure alongside.)
- This contrasts the promised SLA against realized resolution time per priority.

**SLA Breach Rate indicator.**
- Visual: **Card** (or **Gauge** if you want a target). Card value = SLA Breach
  Rate. For a gauge, set Value = SLA Breach Rate, and a target max of your choice.

### Page 4 — External Data (NZ holidays & business days)

**Clustered column — Avg tickets/day by day_type.**
- Visual: **Clustered column chart**
- **X-axis:** `fact_tickets[day_type]` (business day / weekend / holiday)
- **Y-axis (Values):** **Avg Tickets per Day** (this is Total Tickets ÷ distinct
  created dates — the correct per-day normalization).
- Simpler alternative: plot **Total Tickets** by `day_type` instead, but add a
  caption noting the counts aren't day-count-normalized (there are far more
  business days than holidays, so raw totals aren't comparable).

**Card — Tickets on Public Holiday.** Card value = Tickets on Public Holiday.

**Card — Tickets on Regional Anniversary.** Card value = Tickets on Regional
Anniversary.

**Column — business_days_to_resolve distribution.**
- Visual: **Clustered column chart**
- **X-axis:** `fact_tickets[business_days_to_resolve]` (set the field to **Don't
  summarize** so each integer day count is its own category)
- **Y-axis (Values):** Total Tickets.
- This shows how many tickets resolve in 0, 1, 2, … business days.

### Page 5 — Team & Region

**Table / matrix by team.**
- Visual: **Matrix** (or **Table**)
- **Rows:** `fact_tickets[team]`
- **Values:** Total Tickets, SLA Breach Rate, Avg CSAT
- Format: conditional-format SLA Breach Rate and Avg CSAT to rank teams at a
  glance; sort by Total Tickets descending.

**Bar by region.**
- Visual: **Clustered bar chart**
- **Y-axis:** `fact_tickets[region]`
- **X-axis (Values):** Total Tickets · sort descending.
- **Optional Map:** you can instead use a **Map** / **Filled map** with
  `region` on Location and Total Tickets on Size. NZ regions can geocode
  unreliably (ambiguous or non-standard names), so set the field's **Data
  category** to *State or Province* / *Place*, verify the pins, and fall back to
  the bar chart if geocoding is off. Map is optional — the bar chart is the
  dependable default.

### Page 6 — Data Quality

**Clustered column — provided vs recomputed SLA breach.**
- Visual: **Clustered column chart**
- **X-axis:** a simple category or leave blank for a two-bar comparison; the
  cleanest version puts both measures as **Values** on a single-category chart:
  **SLA Breach Rate** and **SLA Breach Rate (Recomputed)**. To compare across a
  dimension, add `priority` or `team` on the X-axis.

**Card — SLA Flag Agreement.** Card value = SLA Flag Agreement (%).

**Card — Resolved Before Created.** Card value = Resolved Before Created (count).

**Text box — reconciliation finding.** Add a **Text box** (Insert ▸ Text box)
with wording along these lines, adjusting the exact percentage to what SLA Flag
Agreement shows in your build:

> **Data-quality note.** The report treats the vendor-provided `sla_breached`
> flag as the system of record for the headline **SLA Breach Rate**. An
> independent recomputation of SLA breach from the raw resolution and target
> times agrees with the provided flag only about **half the time** (see *SLA Flag
> Agreement*). We report on the provided field for consistency with the source
> system, but flag this ~50% divergence: the two definitions disagree materially,
> and the true breach rate is uncertain until the discrepancy is reconciled.
> `Resolved Before Created` surfaces any rows with an impossible timeline as a
> further integrity check.

---

## 6. Theme & polish

- **Theme:** **View** ▸ **Themes** → pick a clean built-in theme (e.g.
  *Executive* or *Innovate*), or import a custom JSON. Keep one accent colour for
  primary series across pages.
- **Number formatting (consistent everywhere):**
  - Resolution Rate, SLA Breach Rate(s), SLA Flag Agreement, Escalation Rate →
    **Percentage**, 1 decimal.
  - Avg Resolution Hours, Avg First Response Hours, Avg Business Days to Resolve →
    **1 decimal**.
  - Avg CSAT → 1–2 decimals. Counts (Total Tickets, etc.) → whole number with
    thousands separator.
- **Titles:** give every visual a short, plain title; give each page a header
  text box or use the page name.
- **Reduce clutter:** turn off gridlines you don't need, hide redundant axis
  titles, disable data labels on dense charts, and keep a consistent font size.
  Turn off **auto date/time** (step 3a) to avoid stray hierarchies.
- Align visuals on a grid (**Format ▸ Snap to grid**); keep the KPI card row
  visually consistent in height.

---

## 7. Publish / deliver

1. **File** ▸ **Save as** → save as **`TechSolve Support Operations.pbix`** in
   the project's **`powerbi/`** folder
   (`D:\Vatsalya PC\All DL\Power BI Assessment\powerbi\`).
2. **Optional — publish to the Power BI Service:** **Home** ▸ **Publish** →
   sign in → choose a workspace. Requires a Power BI account/license; skip if the
   deliverable is the `.pbix` file alone.
3. Do a final pass: open each page, confirm no visual shows an error, the Year
   slicer defaults to 2024 & 2025, and every KPI card renders a value.

Done — the `.pbix` is the deliverable, alongside this guide and
`dax_measures.md`.
