"""
forecast.py  —  a forward-looking value-add (Part 2, "beyond the essentials").

Two honest, ops-relevant projections built on the cleaned data:

1. **Volume forecast.** Monthly ticket volume for the next 6 months, as a baseline
   (mean) model with 80% / 95% prediction intervals. Before forecasting we *test*
   for trend and seasonality — and find essentially none — so a mean/flat baseline
   is the defensible choice, not a spurious trend line. The wide intervals relative
   to the point forecast are the honest signal that this series is near-random.

2. **Business-day capacity projection.** Using the NZ business-day calendar, we
   project expected arrivals per future quarter and the resulting load per *staffed*
   business day (holidays reduce staffed days → higher per-day load). This is the
   part an ops manager can actually act on.

Training window = complete months only (2023-07 … 2024-12). 2025 is excluded from
training: it's an incomplete tail (the export was taken in early 2025), not a
low-volume period.

Output: dashboard_web/forecast.js (window.FORECAST_DATA) + docs/FORECAST_METHODOLOGY.md
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
EXT = ROOT / "data" / "external"
Z80, Z95 = 1.2816, 1.9600
HORIZON = 6                       # months to forecast
FUTURE_QUARTERS = ["2025-Q2", "2025-Q3", "2025-Q4"]


def month_range(start: str, n: int) -> list[str]:
    p = pd.Period(start, freq="M")
    return [str(p + i) for i in range(n)]


def main() -> None:
    df = pd.read_parquet(PROC / "fact_tickets.parquet")

    # complete monthly series: drop the sparse/incomplete 2025 tail
    monthly = (df[df["created_year"] < 2025]
               .groupby("created_month").size().rename("n").reset_index()
               .sort_values("created_month"))
    y = monthly["n"].to_numpy(dtype=float)
    t = np.arange(len(y))

    mean, std = float(y.mean()), float(y.std(ddof=1))
    # trend test: least-squares slope + R^2 (expected ~0 for a flat series)
    slope, intercept = np.polyfit(t, y, 1)
    yhat = slope * t + intercept
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - mean) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    # crude seasonality check: variance explained by calendar-month means
    m = monthly.assign(mo=pd.PeriodIndex(monthly["created_month"], freq="M").month)
    seasonal_range = float(m.groupby("mo")["n"].mean().max() - m.groupby("mo")["n"].mean().min())

    # baseline forecast = mean (no significant trend), PI from monthly std
    fc_months = month_range("2025-01", HORIZON)
    forecast = [{
        "month": mo, "mean": round(mean),
        "lo80": round(mean - Z80 * std), "hi80": round(mean + Z80 * std),
        "lo95": round(mean - Z95 * std), "hi95": round(mean + Z95 * std),
    } for mo in fc_months]

    # daily arrival rate over the training span
    span_days = (df.loc[df["created_year"] < 2025, "created_date"].max()
                 - df.loc[df["created_year"] < 2025, "created_date"].min()).days + 1
    total_train = int(len(df[df["created_year"] < 2025]))
    daily_rate = total_train / span_days

    # capacity projection per future quarter, using the real NZ business-day calendar
    cal = pd.read_csv(EXT / "nz_business_calendar.csv", parse_dates=["date"])
    cal["q"] = cal["year"].astype(str) + "-Q" + cal["quarter"].astype(str)
    capacity = []
    for q in FUTURE_QUARTERS:
        c = cal[cal["q"] == q]
        cal_days = int(len(c))
        biz_days = int(c["is_business_day"].sum())
        holidays = int(c["is_national_holiday"].sum())
        expected = daily_rate * cal_days
        capacity.append({
            "quarter": q, "calendar_days": cal_days, "business_days": biz_days,
            "public_holidays": holidays, "expected_arrivals": round(expected),
            "load_per_business_day": round(expected / biz_days, 1) if biz_days else None,
        })

    data = {
        "history": [{"month": r.created_month, "n": int(r.n)} for r in monthly.itertuples()],
        "forecast": forecast,
        "diagnostics": {
            "n_train_months": len(y), "monthly_mean": round(mean), "monthly_std": round(std),
            "trend_slope_per_month": round(float(slope), 2), "trend_r2": round(r2, 4),
            "seasonal_range": round(seasonal_range), "daily_rate": round(daily_rate, 1),
        },
        "capacity": capacity,
        "note": ("Baseline (mean) forecast: no significant trend or seasonality, so a flat mean is the "
                 "honest model. Monthly volume is also unusually stable (~2% month-to-month), giving a "
                 "confident, narrow band — that low variance is itself a synthetic-data hallmark. The "
                 "actionable output is the capacity projection. Independent of the year filter."),
    }

    payload = json.dumps(data, separators=(",", ":"))
    (ROOT / "dashboard_web" / "forecast.js").write_text(
        f"window.FORECAST_DATA={payload};", encoding="utf-8")
    (ROOT / "dashboard_web" / "forecast.json").write_text(payload, encoding="utf-8")
    write_methodology(data)

    d = data["diagnostics"]
    print(f"train months: {d['n_train_months']}  mean/mo: {d['monthly_mean']:,} +/- {d['monthly_std']:,}")
    print(f"trend slope/mo: {d['trend_slope_per_month']} (R^2 {d['trend_r2']}) -> flat; "
          f"seasonal range {d['seasonal_range']:,}")
    print(f"daily arrival rate: {d['daily_rate']}/day")
    for c in capacity:
        print(f"  {c['quarter']}: ~{c['expected_arrivals']:,} arrivals over {c['business_days']} "
              f"business days ({c['public_holidays']} holidays) -> {c['load_per_business_day']}/business-day")


def write_methodology(data: dict) -> None:
    d = data["diagnostics"]
    md = f"""# Forecast & Capacity — methodology

_A "beyond the essentials" value-add. Generated by `src/forecast.py`._

## Why a baseline (mean) model — not a trend line
Before forecasting I tested the monthly series ({d['n_train_months']} complete months,
2023-07 → 2024-12) for structure:

- **Trend:** least-squares slope = **{d['trend_slope_per_month']} tickets/month** with
  **R² = {d['trend_r2']}** — i.e. time explains essentially none of the variance. There is no
  meaningful trend to extrapolate.
- **Seasonality:** the spread between calendar-month averages is only **{d['seasonal_range']:,}**
  tickets on a **{d['monthly_mean']:,}/month** base — no usable seasonal pattern.

With no trend and no seasonality, the defensible forecast is a **flat baseline at the mean**
({d['monthly_mean']:,}/month), with prediction intervals from the monthly standard deviation
(± {d['monthly_std']:,}). The month-to-month variation is small (**CV ≈ {round(100 * d['monthly_std'] / d['monthly_mean'], 1)}%**),
so the band is **narrow — a confident flat forecast**. That unusually low variance is itself a
hallmark of synthetic data: a real support queue would show growth, seasonality, and more noise.
Fitting a heavier model (ARIMA/Prophet) would add nothing — there is no trend or season to capture.
**The real value here is the capacity projection below**, which turns the stable arrival rate into a
staffing signal.

> 2025 is **excluded from training**: it's an incomplete tail (the export was taken in early 2025),
> not a genuine low-volume period. Forecasting *replaces* it.

## Business-day capacity projection (the actionable part)
Ticket volume is essentially **flat across day types** (business days, weekends, and holidays all
receive ~the same load), so arrivals don't pause on weekends — but staff largely work business days.
Using the real NZ business-day calendar, for each future quarter:

`expected arrivals = daily rate ({d['daily_rate']}/day) × calendar days`, and
`load per staffed day = expected arrivals ÷ business days` (holidays cut business days → higher load).

| Quarter | Expected arrivals | Business days | Public holidays | Load / business day |
|---|---|---|---|---|
""" + "\n".join(
        f"| {c['quarter']} | {c['expected_arrivals']:,} | {c['business_days']} | "
        f"{c['public_holidays']} | {c['load_per_business_day']} |"
        for c in data["capacity"]) + f"""

**Ops takeaway:** arrivals are steady 7 days a week, so each staffed business day must clear roughly
a quarter's arrivals spread over ~{data['capacity'][0]['business_days']} days — and public-holiday
weeks compress that further. Plan cover for holiday periods rather than assuming a weekday peak.
"""
    (ROOT / "docs" / "FORECAST_METHODOLOGY.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
