"""
clean_data.py  —  Part 1 cleaning & preparation for the TechSolve practical.

Reads the raw ticket export, applies documented cleaning rules, joins the NZ
holiday / business-day calendar from fetch_holidays.py, and writes a single tidy
fact table plus a data-quality report that records every transformation.

Design rules (see docs/DESIGN.md §2.2) — kept explicit and auditable:
  * category      : normalise 32 raw variants -> 10 canonical + 5 themes (casing/
                    abbreviation noise only; no semantic guessing).
  * dates         : drop rows whose created-year is outside 2023-2025 (garbage
                    1970/2099); flag the 53 "resolved before created" rows and
                    null their timestamp-derived duration.
  * metrics       : the provided operational fields (resolution_time_hours,
                    sla_breached) are the system-of-record for reporting; we ALSO
                    recompute for comparison and surface the gap (data quality).
  * nulls         : filled with explicit sentinels, never fabricated values.
  * external join : created-date -> day-type (business/weekend/holiday) + regional
                    anniversary flag + business-days-to-resolve.

Outputs:
  data/processed/fact_tickets.csv / .parquet
  data/processed/data_quality_report.json
  docs/DATA_QUALITY_REPORT.md
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "TechSolve - Ticket Data.xlsx"
EXT = ROOT / "data" / "external"
PROC = ROOT / "data" / "processed"
DOCS = ROOT / "docs"

VALID_YEARS = {2023, 2024, 2025}

# ---- category normalisation ------------------------------------------------
# raw variant (lowercased, _->space, collapsed spaces)  ->  canonical label
CANON = {
    "bug report": "Bug Report", "bug": "Bug Report", "bugreport": "Bug Report",
    "login issue": "Login Issue", "loginissue": "Login Issue",
    "payment problem": "Payment Problem", "paymentproblem": "Payment Problem",
    "performance issue": "Performance Issue", "perf issue": "Performance Issue",
    "performanceissue": "Performance Issue",
    "account suspension": "Account Suspension", "acct suspension": "Account Suspension",
    "accountsuspension": "Account Suspension",
    "subscription cancellation": "Subscription Cancellation",
    "subscription cancel": "Subscription Cancellation",
    "sub cancellation": "Subscription Cancellation",
    "subcancellation": "Subscription Cancellation",
    "data sync issue": "Data Sync Issue", "data sync": "Data Sync Issue",
    "datasync": "Data Sync Issue",
    "refund request": "Refund Request", "refund req": "Refund Request",
    "refundrequest": "Refund Request",
    "security concern": "Security Concern", "security": "Security Concern",
    "securityconcern": "Security Concern",
    "feature request": "Feature Request", "feature req": "Feature Request",
    "featurerequest": "Feature Request",
}
CATEGORY_TO_THEME = {
    "Login Issue": "Access & Security", "Security Concern": "Access & Security",
    "Payment Problem": "Billing & Payments", "Refund Request": "Billing & Payments",
    "Account Suspension": "Account Lifecycle",
    "Subscription Cancellation": "Account Lifecycle",
    "Bug Report": "Product & Reliability", "Performance Issue": "Product & Reliability",
    "Data Sync Issue": "Product & Reliability",
    "Feature Request": "Product Feedback",
}


def normalise_category(raw: str) -> str:
    key = " ".join(str(raw).lower().replace("_", " ").split())
    return CANON.get(key, CANON.get(key.replace(" ", ""), None))  # None => unmapped


def load_raw() -> pd.DataFrame:
    return pd.read_excel(RAW, engine="openpyxl")


def clean(df: pd.DataFrame, dq: dict) -> pd.DataFrame:
    dq["rows_in"] = int(len(df))
    df = df.copy()

    # --- 1. category ---------------------------------------------------------
    dq["category_raw_variants"] = int(df["category"].nunique())
    df["category_clean"] = df["category"].map(normalise_category)
    unmapped = df["category_clean"].isna()
    dq["category_unmapped_rows"] = int(unmapped.sum())
    if unmapped.any():  # safety: never silently drop a category we didn't map
        raise ValueError(f"Unmapped categories: {df.loc[unmapped, 'category'].unique()}")
    df["category_changed"] = df["category_clean"] != df["category"]
    dq["category_rows_renormalised"] = int(df["category_changed"].sum())
    dq["category_canonical_count"] = int(df["category_clean"].nunique())
    df["theme"] = df["category_clean"].map(CATEGORY_TO_THEME)

    # --- 2. dates ------------------------------------------------------------
    df["created_year"] = df["ticket_created_date"].dt.year
    bad_year = ~df["created_year"].isin(VALID_YEARS)
    dq["rows_dropped_bad_created_year"] = int(bad_year.sum())
    dq["bad_created_years"] = (df.loc[bad_year, "created_year"]
                               .value_counts().to_dict())
    df = df[~bad_year].copy()

    resolved_before_created = df["ticket_resolved_date"] < df["ticket_created_date"]
    dq["rows_resolved_before_created"] = int(resolved_before_created.sum())
    df["resolved_before_created"] = resolved_before_created
    # only Resolved/Closed tickets are genuinely resolved (all rows carry a
    # resolved_date, even Open/In Progress -> unreliable as a done signal)
    df["is_genuinely_resolved"] = df["status"].isin(["Resolved", "Closed"])

    df["created_date"] = df["ticket_created_date"].dt.normalize()
    df["resolved_date"] = df["ticket_resolved_date"].dt.normalize()
    df["created_month"] = df["ticket_created_date"].dt.to_period("M").astype(str)
    df["created_quarter"] = df["ticket_created_date"].dt.year.astype(str) + "-Q" + \
        df["ticket_created_date"].dt.quarter.astype(str)
    df["created_week"] = df["ticket_created_date"].dt.to_period("W").dt.start_time
    df["created_day_name"] = df["ticket_created_date"].dt.strftime("%a")
    # dates are date-only in this export (no intraday time) -> no hour-of-day analysis
    dq["created_has_intraday_time"] = bool(df["ticket_created_date"].dt.hour.nunique() > 1)

    # timestamp-derived resolution (NaN where integrity fails) — for comparison
    delta_h = (df["ticket_resolved_date"] - df["ticket_created_date"]).dt.total_seconds() / 3600
    df["resolution_hours_calc"] = np.where(resolved_before_created, np.nan, delta_h)

    # --- 3. nulls ------------------------------------------------------------
    fills = {}
    def fill(col, value):
        n = int(df[col].isna().sum())
        if n:
            df[col] = df[col].fillna(value)
        fills[col] = {"filled": n, "value": value}

    fill("account_manager", "Unassigned")
    fill("industry", "Unknown")
    fill("company_name", "Unknown")
    fill("team", "Unassigned")
    fill("assigned_to", "Unassigned")
    fill("resolution_notes", "No notes recorded")
    # browser: N/A for non-web channels, else Unknown
    web_channels = {"Web Form", "Chat"}
    br_null = df["browser"].isna()
    df.loc[br_null & ~df["channel"].isin(web_channels), "browser"] = "N/A (non-web channel)"
    df.loc[df["browser"].isna(), "browser"] = "Unknown"
    fills["browser"] = {"filled": int(br_null.sum()),
                        "value": "N/A (non-web channel) / Unknown"}
    # left null on purpose (PII / excluded from stats)
    fills["billing_contact_email"] = {"filled": 0, "value": "left null (PII, unused)"}
    fills["csat_score"] = {"filled": 0, "value": "left null (excluded from CSAT avg)"}
    dq["null_handling"] = fills

    # --- 4. derived metric fields -------------------------------------------
    df["sla_breached_provided"] = df["sla_breached"].eq("Yes")
    df["sla_breached_recomputed"] = df["resolution_time_hours"] > df["sla_target_hours"]
    df["sla_flags_agree"] = df["sla_breached_provided"] == df["sla_breached_recomputed"]
    df["met_sla"] = ~df["sla_breached_provided"]           # KPI basis = provided field
    df["escalated_flag"] = df["escalated"].eq("Yes")
    df["resolution_bucket"] = pd.cut(
        df["resolution_time_hours"],
        bins=[-0.1, 4, 8, 24, 48, np.inf],
        labels=["0-4h", "4-8h", "8-24h", "24-48h", "48h+"])
    dq["sla_agreement_rate"] = round(float(df["sla_flags_agree"].mean()), 4)
    dq["sla_breach_rate_provided"] = round(float(df["sla_breached_provided"].mean()), 4)
    dq["sla_breach_rate_recomputed"] = round(float(df["sla_breached_recomputed"].mean()), 4)

    # --- 5. external join: calendar + regional anniversaries -----------------
    cal = pd.read_csv(EXT / "nz_business_calendar.csv", parse_dates=["date"])
    cal_flags = cal.set_index("date")[["is_weekend", "is_national_holiday",
                                        "is_business_day", "national_holiday_name"]]
    df = df.merge(cal_flags.rename(columns={
        "is_weekend": "created_is_weekend",
        "is_national_holiday": "created_is_holiday",
        "is_business_day": "created_is_business_day",
        "national_holiday_name": "created_holiday_name",
    }), left_on="created_date", right_index=True, how="left")
    df["day_type"] = np.select(
        [df["created_is_holiday"], df["created_is_weekend"]],
        ["Public Holiday", "Weekend"], default="Business Day")

    # business-days-to-resolve via cumulative business-day index
    cal_sorted = cal.sort_values("date").reset_index(drop=True)
    cal_sorted["bday_index"] = cal_sorted["is_business_day"].cumsum()
    bidx = cal_sorted.set_index("date")["bday_index"]
    cr_idx = df["created_date"].map(bidx)
    rs_idx = df["resolved_date"].map(bidx)
    bdays = rs_idx - cr_idx
    valid = df["is_genuinely_resolved"] & ~df["resolved_before_created"]
    df["business_days_to_resolve"] = np.where(valid, bdays, np.nan)

    # regional anniversary flag
    reg = pd.read_csv(EXT / "nz_regional_anniversaries.csv", parse_dates=["date"])
    reg_keys = set(zip(reg["region"], reg["date"]))
    df["created_on_regional_anniversary"] = [
        (r, d) in reg_keys for r, d in zip(df["region"], df["created_date"])]
    dq["tickets_on_regional_anniversary"] = int(df["created_on_regional_anniversary"].sum())

    dq["rows_out"] = int(len(df))
    dq["created_year_distribution"] = (df["created_year"].value_counts()
                                       .sort_index().to_dict())
    return df


def write_dq_markdown(dq: dict) -> None:
    nulls = "\n".join(
        f"| `{c}` | {v['filled']:,} | {v['value']} |"
        for c, v in dq["null_handling"].items())
    md = f"""# Data Quality Report — TechSolve ticket export

_Generated by `src/clean_data.py`. Every number below is reproducible from the raw file._

## Row accounting
| Stage | Rows |
|---|---|
| Raw input | {dq['rows_in']:,} |
| Dropped — created-year outside 2023-2025 ({dq['bad_created_years']}) | −{dq['rows_dropped_bad_created_year']} |
| **Clean output** | **{dq['rows_out']:,}** |

## Category normalisation
- Raw distinct variants: **{dq['category_raw_variants']}** → canonical categories: **{dq['category_canonical_count']}**
- Rows whose category label was rewritten: **{dq['category_rows_renormalised']:,}**
- Unmapped after normalisation: **{dq['category_unmapped_rows']}** (pipeline fails if > 0)

## Date integrity
- Tickets **resolved before created** (impossible): **{dq['rows_resolved_before_created']}** → timestamp-derived duration set to null for these.
- Note: *every* ticket carries a `resolved_date` regardless of status, so time-to-resolution is computed only for `Resolved`/`Closed` tickets.
- Clean created-year distribution: {dq['created_year_distribution']}

## Metric reconciliation (the headline data-quality finding)
- SLA breach rate — **provided** `sla_breached`: **{dq['sla_breach_rate_provided']:.1%}**
- SLA breach rate — **recomputed** (`resolution_time_hours > sla_target_hours`): **{dq['sla_breach_rate_recomputed']:.1%}**
- The two flags **agree only {dq['sla_agreement_rate']:.1%}** of the time — no better than chance.
- **Decision:** report on the provided (system-of-record) fields; expose this gap in a Data-Quality panel; recommend auditing the source system.

## Null handling (explicit sentinels, no fabricated values)
| Column | Rows filled | Replacement |
|---|---|---|
{nulls}

## External data joined
- Tickets created on their region's **anniversary day**: **{dq['tickets_on_regional_anniversary']:,}**
- Each ticket tagged Business Day / Weekend / Public Holiday, plus business-days-to-resolve.
"""
    (DOCS / "DATA_QUALITY_REPORT.md").write_text(md, encoding="utf-8")


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    dq: dict = {}
    df = clean(load_raw(), dq)

    df.to_parquet(PROC / "fact_tickets.parquet", index=False)
    df.to_csv(PROC / "fact_tickets.csv", index=False)
    (PROC / "data_quality_report.json").write_text(json.dumps(dq, indent=2, default=str),
                                                   encoding="utf-8")
    write_dq_markdown(dq)

    print(f"rows_in={dq['rows_in']:,}  rows_out={dq['rows_out']:,}  "
          f"dropped={dq['rows_dropped_bad_created_year']}")
    print(f"categories: {dq['category_raw_variants']} -> {dq['category_canonical_count']} "
          f"({dq['category_rows_renormalised']:,} rows renormalised)")
    print(f"SLA agreement: {dq['sla_agreement_rate']:.1%}  "
          f"(provided breach {dq['sla_breach_rate_provided']:.1%} vs "
          f"recomputed {dq['sla_breach_rate_recomputed']:.1%})")
    print(f"resolved-before-created flagged: {dq['rows_resolved_before_created']}")
    print(f"on regional anniversary: {dq['tickets_on_regional_anniversary']:,}")
    print(f"cols: {df.shape[1]}  ->  {PROC/'fact_tickets.parquet'}")


if __name__ == "__main__":
    main()
