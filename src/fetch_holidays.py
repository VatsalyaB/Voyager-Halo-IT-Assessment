"""
fetch_holidays.py  —  External data source for the TechSolve practical.

Pulls New Zealand public holidays (national + regional anniversary days) for
2023-2025 from the Nager.Date public API, and derives a per-day business calendar
that the cleaning pipeline joins onto ticket dates.

Why this source:
  - Free, reliable, no key required.
  - Returns *regional* anniversary days (Auckland/Canterbury/Wellington ...) with
    ISO-3166-2 county codes, which join to the ticket `region` column — an
    NZ-specific touch that a generic holiday list can't give us.

Outputs (data/external/):
  - nz_holidays_raw.json        raw API payload (provenance)
  - nz_public_holidays.csv      one row per holiday (national + regional)
  - nz_business_calendar.csv    one row per calendar day 2023-01-01..2025-12-31
                                with weekend / national-holiday / business-day flags

If the API is unreachable, falls back to a hardcoded set of NZ *national* holidays
so the pipeline still runs (regional anniversaries are skipped in that case, and
the fallback is clearly flagged in the output).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd
import requests

YEARS = [2023, 2024, 2025]
COUNTRY = "NZ"
OUT = Path(__file__).resolve().parent.parent / "data" / "external"

# Ticket `region` value  ->  ISO-3166-2 county code(s) used by Nager for NZ.
REGION_TO_COUNTIES = {
    "Auckland": ["NZ-AUK"],
    "Bay of Plenty": ["NZ-BOP"],
    "Canterbury": ["NZ-CAN"],
    "Hawke's Bay": ["NZ-HKB"],
    "Manawatu-Whanganui": ["NZ-MWT"],
    "Nelson-Marlborough": ["NZ-NSN", "NZ-MBH"],
    "Northland": ["NZ-NTL"],
    "Otago": ["NZ-OTA"],
    "Southland": ["NZ-STL"],
    "Taranaki": ["NZ-TKI"],
    "Waikato": ["NZ-WKO"],
    "Wellington": ["NZ-WGN"],
}

# Minimal fallback: NZ national statutory holidays (observed dates, Mondayised).
FALLBACK_NATIONAL = {
    "2023-01-01": "New Year's Day", "2023-01-02": "Day after New Year's Day",
    "2023-01-03": "Day after New Year's Day (observed)",
    "2023-02-06": "Waitangi Day", "2023-04-07": "Good Friday",
    "2023-04-10": "Easter Monday", "2023-04-25": "Anzac Day",
    "2023-06-05": "King's Birthday", "2023-07-14": "Matariki",
    "2023-10-23": "Labour Day", "2023-12-25": "Christmas Day",
    "2023-12-26": "Boxing Day",
    "2024-01-01": "New Year's Day", "2024-01-02": "Day after New Year's Day",
    "2024-02-06": "Waitangi Day", "2024-03-29": "Good Friday",
    "2024-04-01": "Easter Monday", "2024-04-25": "Anzac Day",
    "2024-06-03": "King's Birthday", "2024-06-28": "Matariki",
    "2024-10-28": "Labour Day", "2024-12-25": "Christmas Day",
    "2024-12-26": "Boxing Day",
    "2025-01-01": "New Year's Day", "2025-01-02": "Day after New Year's Day",
    "2025-02-06": "Waitangi Day", "2025-04-18": "Good Friday",
    "2025-04-21": "Easter Monday", "2025-04-25": "Anzac Day",
    "2025-06-02": "King's Birthday", "2025-06-20": "Matariki",
    "2025-10-27": "Labour Day", "2025-12-25": "Christmas Day",
    "2025-12-26": "Boxing Day",
}


def fetch_live() -> tuple[list[dict], bool]:
    """Return (holiday_records, used_live). Falls back to hardcoded national set."""
    raw = []
    try:
        for year in YEARS:
            url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{COUNTRY}"
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            raw.extend(resp.json())
        (OUT / "nz_holidays_raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return raw, True
    except Exception as exc:  # noqa: BLE001 - any network/parse failure -> fallback
        print(f"[warn] live fetch failed ({exc!r}); using hardcoded national fallback", file=sys.stderr)
        raw = [
            {"date": d, "name": n, "localName": n, "global": True, "counties": None}
            for d, n in FALLBACK_NATIONAL.items()
        ]
        return raw, False


def build_holidays_table(raw: list[dict], used_live: bool) -> pd.DataFrame:
    rows = []
    for h in raw:
        counties = h.get("counties")
        rows.append({
            "date": pd.to_datetime(h["date"]).normalize(),
            "holiday_name": h.get("name"),
            "local_name": h.get("localName"),
            "is_national": bool(h.get("global")) or counties is None,
            "counties": ";".join(counties) if counties else "",
            "scope": "National" if (h.get("global") or counties is None) else "Regional",
            "source": "Nager.Date" if used_live else "fallback",
        })
    df = pd.DataFrame(rows).drop_duplicates(subset=["date", "holiday_name", "counties"])
    return df.sort_values("date").reset_index(drop=True)


def build_business_calendar(holidays: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar day; national holidays drive the business-day flag."""
    days = pd.date_range("2023-01-01", "2025-12-31", freq="D")
    national_dates = set(holidays.loc[holidays["is_national"], "date"])
    cal = pd.DataFrame({"date": days})
    cal["year"] = cal["date"].dt.year
    cal["quarter"] = cal["date"].dt.quarter
    cal["month"] = cal["date"].dt.month
    cal["month_name"] = cal["date"].dt.strftime("%b")
    cal["week"] = cal["date"].dt.isocalendar().week.astype(int)
    cal["day_of_week"] = cal["date"].dt.dayofweek  # 0=Mon
    cal["day_name"] = cal["date"].dt.strftime("%a")
    cal["is_weekend"] = cal["day_of_week"] >= 5
    cal["is_national_holiday"] = cal["date"].isin(national_dates)
    cal["is_business_day"] = ~cal["is_weekend"] & ~cal["is_national_holiday"]
    # name the national holiday on that day, if any
    name_map = (holidays[holidays["is_national"]]
                .drop_duplicates("date").set_index("date")["holiday_name"])
    cal["national_holiday_name"] = cal["date"].map(name_map).fillna("")
    return cal


def region_holiday_map(holidays: pd.DataFrame) -> pd.DataFrame:
    """Explode regional anniversaries to (region, date) so ops can join by region."""
    reg = holidays[~holidays["is_national"]].copy()
    out = []
    for _, r in reg.iterrows():
        codes = set(r["counties"].split(";")) if r["counties"] else set()
        for region, region_codes in REGION_TO_COUNTIES.items():
            if codes & set(region_codes):
                out.append({"region": region, "date": r["date"],
                            "holiday_name": r["holiday_name"]})
    cols = ["region", "date", "holiday_name"]
    if not out:  # offline fallback has national holidays only -> empty regional map
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(out).drop_duplicates().sort_values(["region", "date"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw, used_live = fetch_live()
    holidays = build_holidays_table(raw, used_live)
    calendar = build_business_calendar(holidays)
    regional = region_holiday_map(holidays)

    holidays.to_csv(OUT / "nz_public_holidays.csv", index=False)
    calendar.to_csv(OUT / "nz_business_calendar.csv", index=False)
    regional.to_csv(OUT / "nz_regional_anniversaries.csv", index=False)

    print(f"source            : {'Nager.Date (live)' if used_live else 'hardcoded fallback'}")
    print(f"holidays total    : {len(holidays)}  (national={holidays['is_national'].sum()}, "
          f"regional={(~holidays['is_national']).sum()})")
    print(f"business calendar : {len(calendar)} days, "
          f"{calendar['is_business_day'].sum()} business / "
          f"{calendar['is_weekend'].sum()} weekend / "
          f"{calendar['is_national_holiday'].sum()} national-holiday")
    print(f"regional map rows : {len(regional)}  "
          f"(regions covered: {regional['region'].nunique() if len(regional) else 0})")
    if len(regional):
        print("\nregional anniversaries by region:")
        print(regional.groupby("region")["date"].count().to_string())


if __name__ == "__main__":
    main()
