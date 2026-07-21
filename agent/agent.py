"""
agent.py  —  the TechSolve support AI agent.

API-agnostic natural-language -> answer over the cleaned ticket data:
  * If ANTHROPIC_API_KEY is set  -> Claude translates the question to DuckDB SQL,
    the query engine runs it (read-only), and Claude summarises the result.
  * Else if OPENAI_API_KEY is set -> same flow via the OpenAI API.
  * Else                          -> deterministic local fallback (query_engine.local_answer),
    so the agent works with no API key at all.

Any LLM or SQL error degrades gracefully to the local engine, so the agent always answers.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass

import pandas as pd

from query_engine import TicketQueryEngine

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

SQL_SYSTEM = (
    "You translate an operations manager's natural-language question into a single "
    "DuckDB SQL query over a table named `tickets`. Return ONLY the SQL — no prose, no "
    "markdown fences. Rules:\n"
    "- SELECT/WITH only; never modify data.\n"
    "- Prefer aggregates (COUNT, AVG, rates) over dumping rows.\n"
    "- Express rates as percentages with ROUND(...,1) and a clear alias.\n"
    "- For SLA use sla_breached_provided; for time-to-resolution filter is_genuinely_resolved.\n"
    "- Always add a sensible ORDER BY and a LIMIT (<=50).\n\n"
    "Schema:\n{schema}"
)
SUMMARY_SYSTEM = (
    "You are a support-operations analyst. Given a manager's question, the SQL that was run, "
    "and the result table, write a concise, direct answer (2-4 sentences). Lead with the "
    "headline number or finding. Mention a caveat only if it matters (e.g. the SLA flag is "
    "known to be unreliable). Do not invent numbers beyond the table."
)


def detect_provider() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return None


def _strip_sql(text: str) -> str:
    text = re.sub(r"^```(?:sql)?|```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    return text.strip()


# ---- Anthropic (Claude) ----------------------------------------------------
def _anthropic_sql(question: str, schema: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=800,
        system=SQL_SYSTEM.format(schema=schema),
        messages=[{"role": "user", "content": question}],
    )
    return _strip_sql(next(b.text for b in resp.content if b.type == "text"))


def _anthropic_summary(question: str, sql: str, df: pd.DataFrame) -> str:
    import anthropic
    client = anthropic.Anthropic()
    table = df.head(30).to_markdown(index=False)
    resp = client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=600, system=SUMMARY_SYSTEM,
        messages=[{"role": "user",
                   "content": f"Question: {question}\n\nSQL:\n{sql}\n\nResult:\n{table}"}],
    )
    return next(b.text for b in resp.content if b.type == "text").strip()


# ---- OpenAI ----------------------------------------------------------------
def _openai_chat(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL, temperature=0, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content.strip()


def _openai_sql(question: str, schema: str) -> str:
    return _strip_sql(_openai_chat(SQL_SYSTEM.format(schema=schema), question, 800))


def _openai_summary(question: str, sql: str, df: pd.DataFrame) -> str:
    table = df.head(30).to_markdown(index=False)
    return _openai_chat(SUMMARY_SYSTEM,
                        f"Question: {question}\n\nSQL:\n{sql}\n\nResult:\n{table}", 600)


@dataclass
class Answer:
    text: str
    df: pd.DataFrame
    sql: str
    mode: str  # "anthropic" | "openai" | "local" | "local (fallback)"


def answer_question(engine: TicketQueryEngine, question: str) -> Answer:
    provider = detect_provider()
    if provider is None:
        text, df, sql = engine.local_answer(question)
        return Answer(text, df, sql, "local")

    try:
        schema = engine.schema_prompt()
        if provider == "anthropic":
            sql = _anthropic_sql(question, schema)
            df = engine.run_select(sql)
            text = _anthropic_summary(question, sql, df)
        else:  # openai
            sql = _openai_sql(question, schema)
            df = engine.run_select(sql)
            text = _openai_summary(question, sql, df)
        return Answer(text, df, sql, provider)
    except Exception as exc:  # noqa: BLE001 - never leave the manager without an answer
        text, df, sql = engine.local_answer(question)
        return Answer(f"[LLM path failed: {exc}. Answered with the local engine.]\n\n{text}",
                      df, sql, "local (fallback)")


if __name__ == "__main__":
    eng = TicketQueryEngine()
    print("provider:", detect_provider() or "none (local fallback)")
    for q in ["Which categories have the worst SLA breach rate?",
              "How many tickets did we get each month?"]:
        a = answer_question(eng, q)
        print(f"\nQ: {q}\n[{a.mode}] {a.text}\nSQL: {a.sql}")
