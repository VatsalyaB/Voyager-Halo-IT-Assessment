"""
app.py  —  Streamlit chat UI for the TechSolve support AI agent.

Run:  streamlit run app.py
The agent uses Claude or OpenAI if a key is set (ANTHROPIC_API_KEY / OPENAI_API_KEY),
otherwise a deterministic local engine — so it works with no key.
"""
from __future__ import annotations
import streamlit as st

from query_engine import TicketQueryEngine
from agent import answer_question, detect_provider

st.set_page_config(page_title="TechSolve Support Agent", page_icon="🎫", layout="wide")


@st.cache_resource
def get_engine() -> TicketQueryEngine:
    return TicketQueryEngine()


engine = get_engine()
provider = detect_provider()

MODE_LABEL = {
    "anthropic": "🧠 Claude (text-to-SQL)",
    "openai": "🧠 OpenAI (text-to-SQL)",
    None: "⚙️ Local engine (no API key)",
}

with st.sidebar:
    st.header("TechSolve Support Agent")
    st.caption("Ask operational questions about the support tickets in plain English.")
    st.markdown(f"**Mode:** {MODE_LABEL[provider]}")
    st.markdown(f"**Rows:** {engine.n_rows:,} cleaned tickets")
    if provider is None:
        st.info("Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` to enable full "
                "natural-language querying. The local engine still answers common questions.")
    st.divider()
    st.markdown("**Try asking**")
    examples = [
        "Which categories have the worst SLA breach rate?",
        "How many tickets did we get each month?",
        "Team performance — volume, breach rate and CSAT",
        "Average resolution time by priority",
        "Escalation rate by service area",
        "How many tickets in 2024?",
        "Average CSAT by region",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex}", use_container_width=True):
            st.session_state["pending"] = ex

st.title("🎫 TechSolve Support Agent")

if "history" not in st.session_state:
    st.session_state["history"] = []

# replay history
for turn in st.session_state["history"]:
    with st.chat_message("user"):
        st.write(turn["q"])
    with st.chat_message("assistant"):
        st.write(turn["a"].text)
        if turn["a"].df is not None and len(turn["a"].df):
            st.dataframe(turn["a"].df, use_container_width=True, hide_index=True)
        if turn["a"].sql:
            with st.expander("SQL used"):
                st.code(turn["a"].sql, language="sql")
        st.caption(f"answered via: {turn['a'].mode}")

prompt = st.chat_input("Ask about ticket trends, team performance, SLA, CSAT…")
if "pending" in st.session_state and not prompt:
    prompt = st.session_state.pop("pending")

if prompt:
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Querying the ticket data…"):
            ans = answer_question(engine, prompt)
        st.write(ans.text)
        if ans.df is not None and len(ans.df):
            st.dataframe(ans.df, use_container_width=True, hide_index=True)
        if ans.sql:
            with st.expander("SQL used"):
                st.code(ans.sql, language="sql")
        st.caption(f"answered via: {ans.mode}")
    st.session_state["history"].append({"q": prompt, "a": ans})
