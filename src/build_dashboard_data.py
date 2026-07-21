"""
build_dashboard_data.py  —  pre-aggregate the fact table into a compact JSON the
web dashboard loads instantly (no 100k rows in the browser).

Every dimension is aggregated per (value, year) as a bundle of sums & counts, so the
dashboard's year filter recomputes rates/averages client-side for any year selection
(default = 2024-2025, toggle = all years).

Output: dashboard_web/data.json
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "dashboard_web" / "data.json"

DIMS = ["theme", "category_clean", "status", "priority", "service_area",
        "channel", "team", "region", "day_type", "resolution_bucket", "created_month"]


def bundle(g: pd.DataFrame) -> dict:
    resolved = g[g["is_genuinely_resolved"]]
    csat = g["csat_score"].dropna()
    bdays = g["business_days_to_resolve"].dropna()
    return {
        "n": int(len(g)),
        "breach_n": int(g["sla_breached_provided"].sum()),
        "esc_n": int(g["escalated_flag"].sum()),
        "resolved_n": int(g["is_genuinely_resolved"].sum()),
        "res_sum": float(resolved["resolution_time_hours"].sum()),
        "res_n": int(resolved["resolution_time_hours"].notna().sum()),
        "ffr_sum": float(g["first_response_time_hours"].sum()),
        "ffr_n": int(g["first_response_time_hours"].notna().sum()),
        "csat_sum": float(csat.sum()),
        "csat_n": int(csat.notna().sum()),
        "bdays_sum": float(bdays.sum()),
        "bdays_n": int(bdays.notna().sum()),
    }


def agg_dim(df: pd.DataFrame, col: str) -> list[dict]:
    out = []
    for (val, yr), g in df.groupby([col, "created_year"], observed=True):
        rec = {"value": str(val), "year": int(yr)}
        rec.update(bundle(g))
        out.append(rec)
    return out


def main() -> None:
    df = pd.read_parquet(PROC / "fact_tickets.parquet")
    dq = json.loads((PROC / "data_quality_report.json").read_text(encoding="utf-8"))

    data = {
        "meta": {
            "rows_total": int(len(df)),
            "years": sorted(int(y) for y in df["created_year"].unique()),
            "window_default": [2024, 2025],
            "generated_from": "data/processed/fact_tickets.parquet",
        },
        "kpi_by_year": {},
        "dims": {},
        "daytype_daycounts": {},
        "bdays_hist": {},
        "sla_target_by_priority": {},
        "dq": {
            "sla_breach_provided": dq["sla_breach_rate_provided"],
            "sla_breach_recomputed": dq["sla_breach_rate_recomputed"],
            "sla_agreement_rate": dq["sla_agreement_rate"],
            "resolved_before_created": dq["rows_resolved_before_created"],
            "rows_dropped_bad_year": dq["rows_dropped_bad_created_year"],
            "category_rows_renormalised": dq["category_rows_renormalised"],
            "category_raw_variants": dq["category_raw_variants"],
            "rows_in": dq["rows_in"],
            "rows_out": dq["rows_out"],
        },
    }

    # KPI totals per year
    for yr, g in df.groupby("created_year"):
        data["kpi_by_year"][str(int(yr))] = bundle(g)

    # per-dimension aggregates
    for col in DIMS:
        key = "category" if col == "category_clean" else col
        data["dims"][key] = agg_dim(df, col)

    # day-type calendar day counts per year (for avg tickets/day by day type).
    # Clip to the span the ticket data actually covers (2023-07 .. 2025-03) so a year
    # with calendar days but ~no tickets (2025) doesn't inflate the denominator and
    # halve the per-day averages.
    cal = pd.read_csv(ROOT / "data" / "external" / "nz_business_calendar.csv",
                      parse_dates=["date"])
    lo, hi = df["created_date"].min(), df["created_date"].max()
    cal = cal[(cal["date"] >= lo) & (cal["date"] <= hi)]
    cal["day_type"] = np.select(
        [cal["is_national_holiday"], cal["is_weekend"]],
        ["Public Holiday", "Weekend"], default="Business Day")
    for (dt, yr), g in cal.groupby(["day_type", cal["date"].dt.year]):
        data["daytype_daycounts"].setdefault(str(dt), {})[str(int(yr))] = int(len(g))

    # business-days-to-resolve histogram (resolved only) per year
    res = df[df["business_days_to_resolve"].notna()]
    for yr, g in res.groupby("created_year"):
        h = g["business_days_to_resolve"].astype(int).value_counts().sort_index()
        data["bdays_hist"][str(int(yr))] = {int(k): int(v) for k, v in h.items()}

    # avg SLA target vs avg actual resolution by priority (resolved) per year
    for (pr, yr), g in df.groupby(["priority", "created_year"]):
        r = g[g["is_genuinely_resolved"]]
        data["sla_target_by_priority"].setdefault(pr, {})[str(int(yr))] = {
            "target_avg": float(g["sla_target_hours"].mean()),
            "actual_avg": float(r["resolution_time_hours"].mean()) if len(r) else None,
            "breach_rate": float(g["sla_breached_provided"].mean()),
            "n": int(len(g)),
        }

    payload = json.dumps(data, separators=(",", ":"))
    OUT.write_text(payload, encoding="utf-8")
    # also emit as a JS global so index.html works via file:// (script src) not just http
    (OUT.parent / "data.js").write_text(
        f"window.DASHBOARD_DATA={payload};", encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT}  ({size_kb:.0f} KB)  + data.js")
    print(f"years={data['meta']['years']}  dims={list(data['dims'])}")
    print(f"kpi years: {list(data['kpi_by_year'])}")


if __name__ == "__main__":
    main()
