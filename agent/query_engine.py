"""
query_engine.py  —  the data layer the TechSolve AI agent talks to.

Wraps the cleaned fact table in DuckDB and exposes three things:
  * schema_prompt()      a compact schema + allowed categorical values for text-to-SQL
  * run_select(sql)      read-only SQL execution with a safety gate -> DataFrame
  * local_answer(q)      a deterministic keyword router (the no-API-key fallback)

Both the LLM path (agent.py) and the offline fallback run their SQL through the same
safe executor, so the agent can never mutate the data.
"""
from __future__ import annotations
import re
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARQUET = ROOT / "data" / "processed" / "fact_tickets.parquet"

# columns exposed to the agent, with one-line descriptions
COLUMNS = {
    "ticket_id": "unique ticket id",
    "customer_id": "customer id",
    "created_date": "DATE the ticket was created",
    "resolved_date": "DATE the ticket was resolved (present for all rows; only meaningful when status is Resolved/Closed)",
    "created_year": "INT year created (2023-2025)",
    "created_month": "TEXT 'YYYY-MM'",
    "created_quarter": "TEXT 'YYYY-Qn'",
    "created_day_name": "TEXT weekday (Mon..Sun)",
    "category": "cleaned issue category (10 values)",
    "theme": "reporting theme (5 values)",
    "service_area": "product surface (10 values)",
    "priority": "Low/Medium/High/Urgent",
    "status": "Open/In Progress/Pending Customer/Resolved/Closed",
    "team": "handling team",
    "channel": "how the ticket arrived",
    "region": "NZ region",
    "resolution_time_hours": "FLOAT hours to resolve (system field; use for resolved tickets)",
    "first_response_time_hours": "FLOAT hours to first response",
    "sla_target_hours": "INT SLA target (4/8/24/48)",
    "business_days_to_resolve": "FLOAT working days to resolve (excl weekends/holidays)",
    "csat_score": "INT 1-5 satisfaction (nullable)",
    "issue_complexity_score": "INT 1-10",
    "previous_tickets": "INT prior tickets from this customer",
    "monthly_contract_value": "FLOAT customer monthly contract value",
    "met_sla": "BOOLEAN ticket met SLA (= NOT sla_breached_provided)",
    "sla_breached_provided": "BOOLEAN system-of-record SLA breach flag (use this for SLA reporting)",
    "sla_breached_recomputed": "BOOLEAN recomputed breach (resolution_time_hours > sla_target_hours)",
    "escalated_flag": "BOOLEAN ticket was escalated",
    "is_genuinely_resolved": "BOOLEAN status is Resolved or Closed",
    "day_type": "Business Day/Weekend/Public Holiday (NZ calendar, by created date)",
    "created_is_holiday": "BOOLEAN created on an NZ public holiday",
    "created_on_regional_anniversary": "BOOLEAN created on the region's anniversary day",
}
SMALL_CARDINALITY = ["category", "theme", "service_area", "priority", "status",
                     "team", "channel", "region", "day_type"]

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|copy|pragma|install|load|call|"
    r"set|export|import|grant|revoke|truncate)\b", re.IGNORECASE)


class TicketQueryEngine:
    def __init__(self, parquet: Path = PARQUET):
        self.con = duckdb.connect(database=":memory:")
        # expose the CLEANED category as `category` (drop the raw variant column)
        self.con.execute(
            "CREATE TABLE tickets AS SELECT * EXCLUDE (category, category_clean), "
            f"category_clean AS category FROM read_parquet('{parquet.as_posix()}')")
        self.n_rows = self.con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        self._values = {c: [r[0] for r in self.con.execute(
            f'SELECT DISTINCT "{c}" FROM tickets WHERE "{c}" IS NOT NULL ORDER BY 1').fetchall()]
            for c in SMALL_CARDINALITY}

    # ---- schema for the LLM ------------------------------------------------
    def schema_prompt(self) -> str:
        cols = "\n".join(f"  - {c} : {d}" for c, d in COLUMNS.items())
        vals = "\n".join(f"  - {c}: {self._values[c]}" for c in SMALL_CARDINALITY)
        return (
            f"Table `tickets` ({self.n_rows} rows). One row per support ticket.\n"
            f"Columns:\n{cols}\n\n"
            f"Allowed values for categorical columns:\n{vals}\n\n"
            "Guidance: for SLA reporting use sla_breached_provided (the system-of-record "
            "flag). For time-to-resolution, filter is_genuinely_resolved = TRUE. Dates are "
            "real DATEs. Rates should be returned as fractions or percentages with a label."
        )

    # ---- safe execution ----------------------------------------------------
    def run_select(self, sql: str, max_rows: int = 1000) -> pd.DataFrame:
        s = sql.strip().rstrip(";").strip()
        low = s.lower()
        if not (low.startswith("select") or low.startswith("with")):
            raise ValueError("Only SELECT/WITH queries are allowed.")
        if ";" in s:
            raise ValueError("Only a single statement is allowed.")
        if _FORBIDDEN.search(s):
            raise ValueError("Query contains a forbidden keyword (read-only access only).")
        if not re.search(r"\blimit\b", low):
            s += f" LIMIT {max_rows}"
        return self.con.execute(s).fetchdf()

    # ---- deterministic fallback (no API key) -------------------------------
    def local_answer(self, q: str) -> tuple[str, pd.DataFrame, str]:
        ql = q.lower()

        def dim_for() -> str | None:
            for kw, col in [("categor", "category"), ("theme", "theme"),
                            ("service", "service_area"), ("team", "team"),
                            ("region", "region"), ("priorit", "priority"),
                            ("status", "status"), ("channel", "channel"),
                            ("day type", "day_type"), ("holiday", "day_type")]:
                if kw in ql:
                    return col
            return None

        year_filter = ""
        m = re.search(r"\b(2023|2024|2025)\b", ql)
        if m:
            year_filter = f" WHERE created_year = {m.group(1)}"

        # --- trend over time ---
        if any(k in ql for k in ["trend", "over time", "by month", "monthly", "each month"]):
            sql = (f"SELECT created_month, COUNT(*) AS tickets FROM tickets{year_filter} "
                   f"GROUP BY created_month ORDER BY created_month")
            df = self.run_select(sql)
            return (f"Ticket volume by month ({len(df)} months). "
                    f"Peak: {df.loc[df['tickets'].idxmax(),'created_month']} "
                    f"({int(df['tickets'].max()):,}).", df, sql)

        # --- SLA breach ---
        if "sla" in ql or "breach" in ql:
            col = dim_for()
            if col:
                sql = (f"SELECT {col}, COUNT(*) AS tickets, "
                       f"ROUND(100.0*AVG(CASE WHEN sla_breached_provided THEN 1 ELSE 0 END),1) AS breach_pct "
                       f"FROM tickets{year_filter} GROUP BY {col} ORDER BY breach_pct DESC")
                df = self.run_select(sql)
                return (f"SLA breach rate by {col} (system-of-record flag).", df, sql)
            sql = (f"SELECT ROUND(100.0*AVG(CASE WHEN sla_breached_provided THEN 1 ELSE 0 END),1) AS breach_pct, "
                   f"COUNT(*) AS tickets FROM tickets{year_filter}")
            df = self.run_select(sql)
            return (f"Overall SLA breach rate: {df['breach_pct'][0]}% "
                    f"(provided flag; note it agrees with a recomputation only ~50% of the time).", df, sql)

        # --- CSAT ---
        if "csat" in ql or "satisf" in ql:
            col = dim_for()
            grp = f", {col}" if col else ""
            sel = f"{col}, " if col else ""
            sql = (f"SELECT {sel}ROUND(AVG(csat_score),2) AS avg_csat, COUNT(csat_score) AS responses "
                   f"FROM tickets{year_filter}" + (f" GROUP BY {col} ORDER BY avg_csat DESC" if col else ""))
            df = self.run_select(sql)
            return ("Average CSAT" + (f" by {col}." if col else f": {df['avg_csat'][0]} / 5."), df, sql)

        # --- resolution time ---
        if any(k in ql for k in ["resolution time", "how long", "time to resolve", "resolve time", "resolution hours"]):
            col = dim_for()
            sel = f"{col}, " if col else ""
            gb = f" GROUP BY {col} ORDER BY avg_hours DESC" if col else ""
            sql = (f"SELECT {sel}ROUND(AVG(resolution_time_hours),1) AS avg_hours, "
                   f"ROUND(AVG(business_days_to_resolve),1) AS avg_business_days, COUNT(*) AS tickets "
                   f"FROM tickets WHERE is_genuinely_resolved{year_filter.replace('WHERE','AND')}{gb}")
            df = self.run_select(sql)
            return ("Average time to resolution (resolved/closed tickets)" + (f" by {col}." if col else "."), df, sql)

        # --- escalation ---
        if "escalat" in ql:
            col = dim_for()
            sel = f"{col}, " if col else ""
            gb = f" GROUP BY {col} ORDER BY esc_pct DESC" if col else ""
            sql = (f"SELECT {sel}ROUND(100.0*AVG(CASE WHEN escalated_flag THEN 1 ELSE 0 END),1) AS esc_pct, "
                   f"COUNT(*) AS tickets FROM tickets{year_filter}{gb}")
            df = self.run_select(sql)
            return ("Escalation rate" + (f" by {col}." if col else f": {df['esc_pct'][0]}%."), df, sql)

        # --- generic breakdown / top-N by a dimension ---
        col = dim_for()
        if col or any(k in ql for k in ["how many", "count", "total", "most", "top", "breakdown", "volume", "by "]):
            if col:
                sql = (f"SELECT {col}, COUNT(*) AS tickets FROM tickets{year_filter} "
                       f"GROUP BY {col} ORDER BY tickets DESC")
                df = self.run_select(sql)
                return (f"Ticket count by {col}. Top: {df[col][0]} ({int(df['tickets'][0]):,}).", df, sql)
            sql = f"SELECT COUNT(*) AS tickets FROM tickets{year_filter}"
            df = self.run_select(sql)
            return (f"Total tickets{(' in '+m.group(1)) if m else ''}: {int(df['tickets'][0]):,}.", df, sql)

        # --- help ---
        help_df = pd.DataFrame({"try asking": [
            "How many tickets by category?", "SLA breach rate by team",
            "Ticket trend over time", "Average CSAT by region",
            "Resolution time by priority", "Escalation rate by service area",
            "How many tickets in 2024?"]})
        return ("I can answer operational questions about the tickets. I couldn't map that one "
                "to a query — here are examples that work:", help_df, "")


if __name__ == "__main__":
    eng = TicketQueryEngine()
    for q in ["How many tickets by category?", "SLA breach rate by team",
              "ticket trend over time", "average csat by region",
              "resolution time by priority", "how many tickets in 2024?"]:
        txt, df, sql = eng.local_answer(q)
        print(f"\nQ: {q}\n-> {txt}\nSQL: {sql}\n{df.head(4).to_string(index=False)}")
