"""
build_star_schema.py  —  turn the cleaned fact table into a Power BI-ready star schema.

Reads data/processed/fact_tickets.parquet and emits a slim fact plus conformed
dimensions to data/processed/star/. The BUILD_GUIDE wires these together in Power BI:

    dim_date (date) 1───* fact_tickets (created_date)
    dim_customer (customer_id) 1───* fact_tickets (customer_id)
    dim_category (category) 1───* fact_tickets (category)

Low-cardinality attributes (priority, status, channel, team, service_area, region)
stay on the fact as native columns — Power BI slices them directly without a dim.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
STAR = PROC / "star"

FACT_COLS = [
    "ticket_id", "customer_id", "created_date", "resolved_date",
    "created_month", "created_quarter", "created_week", "created_day_name",
    "category_clean", "theme", "service_area", "priority", "status", "team",
    "assigned_to", "channel", "region", "day_type",
    # measures
    "resolution_time_hours", "first_response_time_hours", "sla_target_hours",
    "resolution_hours_calc", "business_days_to_resolve",
    "csat_score", "issue_complexity_score", "previous_tickets",
    "monthly_contract_value",
    # flags
    "met_sla", "sla_breached_provided", "sla_breached_recomputed", "sla_flags_agree",
    "escalated_flag", "is_genuinely_resolved", "resolved_before_created",
    "created_is_weekend", "created_is_holiday", "created_is_business_day",
    "created_on_regional_anniversary", "created_holiday_name",
]


def build_dim_customer(df: pd.DataFrame) -> pd.DataFrame:
    attrs = ["customer_name", "company_name", "account_type", "customer_segment",
             "industry", "region", "subscription_type", "customer_tenure_months",
             "monthly_contract_value", "account_manager", "account_created_date"]
    # most frequent value per customer (attributes can vary across a customer's tickets)
    def mode_first(s):
        m = s.mode()
        return m.iloc[0] if len(m) else s.iloc[0]
    dim = df.groupby("customer_id")[attrs].agg(mode_first).reset_index()
    return dim


def build_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    cal = pd.read_csv(ROOT / "data" / "external" / "nz_business_calendar.csv",
                      parse_dates=["date"])
    # restrict to the span actually present in the tickets, +/- a little headroom
    lo, hi = df["created_date"].min(), df["resolved_date"].max()
    cal = cal[(cal["date"] >= lo) & (cal["date"] <= hi)].copy()
    cal["day_type"] = (cal["is_national_holiday"].map({True: "Public Holiday"})
                       .fillna(cal["is_weekend"].map({True: "Weekend"}))
                       .fillna("Business Day"))
    return cal.rename(columns={"date": "date"})


def main() -> None:
    STAR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(PROC / "fact_tickets.parquet")

    fact = df[FACT_COLS].copy()
    dim_customer = build_dim_customer(df)
    dim_category = (df[["category_clean", "theme"]].drop_duplicates()
                    .sort_values(["theme", "category_clean"])
                    .rename(columns={"category_clean": "category"}))
    dim_date = build_dim_date(df)

    fact = fact.rename(columns={"category_clean": "category"})
    fact.to_csv(STAR / "fact_tickets.csv", index=False)
    dim_customer.to_csv(STAR / "dim_customer.csv", index=False)
    dim_category.to_csv(STAR / "dim_category.csv", index=False)
    dim_date.to_csv(STAR / "dim_date.csv", index=False)

    print(f"fact_tickets : {fact.shape[0]:,} rows x {fact.shape[1]} cols")
    print(f"dim_customer : {dim_customer.shape[0]:,} customers x {dim_customer.shape[1]} cols")
    print(f"dim_category : {dim_category.shape[0]} rows (theme/category)")
    print(f"dim_date     : {dim_date.shape[0]:,} days ({dim_date['date'].min().date()} "
          f"-> {dim_date['date'].max().date()})")
    print(f"written to   : {STAR}")


if __name__ == "__main__":
    main()
