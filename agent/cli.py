"""
cli.py  —  terminal interface to the TechSolve support agent.

Handy for a quick demo/recording without Streamlit, and for reviewers who just
want to try questions from a shell.

Usage:
  python cli.py                       # interactive REPL
  python cli.py "how many tickets by team?"   # one-shot
"""
from __future__ import annotations
import sys

from query_engine import TicketQueryEngine
from agent import answer_question, detect_provider


def show(ans) -> None:
    print(f"\n\033[1m{ans.text}\033[0m")
    if ans.df is not None and len(ans.df):
        print()
        print(ans.df.head(15).to_string(index=False))
    if ans.sql:
        print(f"\n\033[2mSQL: {ans.sql}\033[0m")
    print(f"\033[2m[answered via: {ans.mode}]\033[0m")


def main() -> None:
    engine = TicketQueryEngine()
    print(f"TechSolve Support Agent  |  {engine.n_rows:,} cleaned tickets  |  "
          f"mode: {detect_provider() or 'local (no API key)'}")

    if len(sys.argv) > 1:
        show(answer_question(engine, " ".join(sys.argv[1:])))
        return

    print("Ask a question (or 'quit'). Examples: 'sla breach by team', "
          "'ticket trend', 'csat by region'.")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye"); return
        if q.lower() in {"quit", "exit", "q", ""}:
            print("bye"); return
        show(answer_question(engine, q))


if __name__ == "__main__":
    main()
