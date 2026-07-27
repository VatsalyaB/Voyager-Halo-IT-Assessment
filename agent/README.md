# AI Agent (Part 3)

A natural-language agent that answers operational questions about the TechSolve
support data. **API-agnostic with an offline fallback**, so it runs with or without
an LLM key.

## How it works
```
question ──▶ agent.py ──▶ (LLM path)  NL → DuckDB SQL → run (read-only) → NL summary
                     └──▶ (local path) keyword router → parameterized SQL → templated answer
```
- **With `ANTHROPIC_API_KEY`** → Claude (`claude-opus-4-8` by default) writes the SQL and summarizes.
- **With `OPENAI_API_KEY`** → same flow via OpenAI.
- **With neither** → a deterministic intent parser handles the common question types
  (volume, trends, SLA, CSAT, resolution time, escalation, by category/team/region/…).
- Every path runs SQL through the **same read-only safety gate** (`query_engine.py`):
  SELECT/WITH only, single statement, forbidden-keyword block, auto-LIMIT. The agent
  can never modify the data.

## Files
- `query_engine.py` - DuckDB over `data/processed/fact_tickets.parquet`; schema prompt,
  safe executor, and the local fallback engine.
- `agent.py` - provider detection + Claude/OpenAI adapters + graceful degradation.
- `app.py` - Streamlit chat UI (shows the answer, the result table, and the SQL used).
- `cli.py` - terminal interface (interactive or one-shot).

## Run it
```bash
# from the project root, using the project venv
pip install -r requirements.txt

# Web UI
streamlit run agent/app.py

# Terminal
python agent/cli.py                       # REPL
python agent/cli.py "sla breach rate by team"

# Optional - enable the LLM path
setx ANTHROPIC_API_KEY "sk-ant-..."       # Windows; or OPENAI_API_KEY
# (optional model override) setx ANTHROPIC_MODEL "claude-haiku-4-5"
```

## Example questions
- "Which categories have the worst SLA breach rate?"
- "How many tickets did we get each month?"
- "Team performance - volume, breach rate and CSAT"
- "Average resolution time by priority"
- "Escalation rate by service area" · "Average CSAT by region" · "How many tickets in 2024?"

See `docs/screenshots/agent-demo.png` for the running UI.
