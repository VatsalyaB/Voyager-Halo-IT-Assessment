# DAX Measures - TechSolve Support Operations

Create these as **measures** (not calculated columns) in Power BI Desktop. The
recommended home is a dedicated, empty **`_Measures`** table (see
`BUILD_GUIDE.md`, step 4), but you can also place them on `fact_tickets`.

**How to add a measure:** select the target table in the **Data** or **Model**
pane → **Table tools** ▸ **New measure** (or right-click the table ▸ *New
measure*) → paste the whole `Name = expression` block into the formula bar →
press **Enter** → click the ✓. Repeat for each measure below.

### Boolean columns - read this first

Several measures filter on boolean columns (`is_genuinely_resolved`,
`sla_breached_provided`, `escalated_flag`, etc.). These arrive from pandas as the
**text** `"True"` / `"False"`. In Power Query, set each of these columns to type
**True/False (Boolean)** so the comparisons below work as written.

- If a column **is** typed True/False → use `= TRUE()` (as shown).
- If you left a column as **text** → replace `= TRUE()` with `= "True"` in that
  measure (e.g. `fact_tickets[is_genuinely_resolved] = "True"`).

Do not mix the two forms: `TRUE()` will not match the text `"True"`, and vice
versa. Confirm the column types before trusting any rate below.

---

## Core volume & resolution

### Total Tickets
The base count every other measure builds on. Counts all rows in the fact table
within the current filter context.

```dax
Total Tickets = COUNTROWS ( fact_tickets )
```

### Resolved Tickets
Count of tickets flagged as genuinely resolved.

```dax
Resolved Tickets =
CALCULATE (
    [Total Tickets],
    fact_tickets[is_genuinely_resolved] = TRUE ()
)
```

### Resolution Rate
Share of tickets that were genuinely resolved. `DIVIDE` returns blank (not an
error) on a zero denominator. **Format as Percentage.**

```dax
Resolution Rate = DIVIDE ( [Resolved Tickets], [Total Tickets] )
```

### Avg Resolution Hours
Average `resolution_time_hours`, restricted to genuinely-resolved tickets so
unresolved rows don't distort the mean. **Format to 1 decimal.**

```dax
Avg Resolution Hours =
CALCULATE (
    AVERAGE ( fact_tickets[resolution_time_hours] ),
    fact_tickets[is_genuinely_resolved] = TRUE ()
)
```

### Avg First Response Hours
Average time to first response across all tickets. `AVERAGE` ignores blanks
automatically. **Format to 1 decimal.**

```dax
Avg First Response Hours = AVERAGE ( fact_tickets[first_response_time_hours] )
```

---

## SLA measures

### SLA Breach Rate
Share of tickets that breached SLA, using the **provided** breach flag
(`sla_breached_provided`) - treat this as the system-of-record figure.
**Format as Percentage.**

```dax
SLA Breach Rate =
DIVIDE (
    CALCULATE ( [Total Tickets], fact_tickets[sla_breached_provided] = TRUE () ),
    [Total Tickets]
)
```

### SLA Breach Rate (Recomputed)
Same calculation against the **independently recomputed** flag
(`sla_breached_recomputed`). Used on the Data Quality page to expose the gap
versus the provided flag. **Format as Percentage.**

```dax
SLA Breach Rate (Recomputed) =
DIVIDE (
    CALCULATE ( [Total Tickets], fact_tickets[sla_breached_recomputed] = TRUE () ),
    [Total Tickets]
)
```

### SLA Flag Agreement
Share of tickets where the provided and recomputed SLA flags **agree**
(`sla_flags_agree`). A low value signals the two definitions diverge.
**Format as Percentage.**

```dax
SLA Flag Agreement =
DIVIDE (
    CALCULATE ( [Total Tickets], fact_tickets[sla_flags_agree] = TRUE () ),
    [Total Tickets]
)
```

---

## Experience & escalation

### Avg CSAT
Average customer-satisfaction score. `AVERAGE` **ignores blanks automatically**,
so tickets with no CSAT survey are excluded from the mean (they don't count as
zero). **Format to 1–2 decimals.**

```dax
Avg CSAT = AVERAGE ( fact_tickets[csat_score] )
```

### Escalation Rate
Share of tickets that were escalated (`escalated_flag`). **Format as Percentage.**

```dax
Escalation Rate =
DIVIDE (
    CALCULATE ( [Total Tickets], fact_tickets[escalated_flag] = TRUE () ),
    [Total Tickets]
)
```

---

## Operational timing

### Avg Business Days to Resolve
Average `business_days_to_resolve`, excludes NZ weekends/holidays from the
elapsed-time count. **Format to 1 decimal.**

```dax
Avg Business Days to Resolve = AVERAGE ( fact_tickets[business_days_to_resolve] )
```

---

## Data-quality & external-data measures

### Resolved Before Created
Count of tickets whose `resolved_date` precedes their `created_date` - a logical
impossibility and a data-integrity red flag. Expect this to be low; any non-zero
value is worth calling out. **Format as Whole Number.**

```dax
Resolved Before Created =
CALCULATE ( [Total Tickets], fact_tickets[resolved_before_created] = TRUE () )
```

### Tickets on Public Holiday
Count of tickets created on an NZ public holiday (`created_is_holiday`).
**Format as Whole Number.**

```dax
Tickets on Public Holiday =
CALCULATE ( [Total Tickets], fact_tickets[created_is_holiday] = TRUE () )
```

### Tickets on Regional Anniversary
Count of tickets created on a regional anniversary day
(`created_on_regional_anniversary`). **Format as Whole Number.**

```dax
Tickets on Regional Anniversary =
CALCULATE ( [Total Tickets], fact_tickets[created_on_regional_anniversary] = TRUE () )
```

### Avg Tickets per Day
Average daily ticket volume: total tickets divided by the number of **distinct
creation dates** present in the current filter context. Pair it with `day_type`
(business day / weekend / holiday) to compare load per day across day types.
**Format to 1 decimal.**

```dax
Avg Tickets per Day =
DIVIDE ( [Total Tickets], DISTINCTCOUNT ( fact_tickets[created_date] ) )
```

> Note: `DISTINCTCOUNT` counts distinct **dates that actually appear** in the
> filtered fact rows. If a day type has days with zero tickets, those empty days
> are not in the fact table and so are not counted - the "per day" average is
> over days that had at least one ticket. That is the intended reading here.

---

## Measure checklist

| # | Measure | Format |
|---|---------|--------|
| 1 | Total Tickets | Whole number |
| 2 | Resolved Tickets | Whole number |
| 3 | Resolution Rate | Percentage |
| 4 | Avg Resolution Hours | 1 decimal |
| 5 | Avg First Response Hours | 1 decimal |
| 6 | SLA Breach Rate | Percentage |
| 7 | SLA Breach Rate (Recomputed) | Percentage |
| 8 | SLA Flag Agreement | Percentage |
| 9 | Avg CSAT | 1–2 decimals |
| 10 | Escalation Rate | Percentage |
| 11 | Avg Business Days to Resolve | 1 decimal |
| 12 | Resolved Before Created | Whole number |
| 13 | Tickets on Public Holiday | Whole number |
| 14 | Tickets on Regional Anniversary | Whole number |
| 15 | Avg Tickets per Day | 1 decimal |
