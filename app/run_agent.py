"""
SLA Monitoring Agent - command line.

  python run_agent.py report            build today's report (reports/*.md + *.html)
  python run_agent.py report --send     ... and e-mail / post it (configure app/.env)
  python run_agent.py ask "Why did SLA drop in March?"
  python run_agent.py chat              interactive chat in the terminal
  python run_agent.py risk              open tickets most likely to breach (ML)
  python run_agent.py doctor            check settings and the LLM connection
"""
import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")          # emojis / arrows in a Windows console
except Exception:
    pass

from agent import SLAAgent                              # noqa: E402


def show(r):
    print("\n" + r["answer"])
    tools = ", ".join(t["tool"] for t in r.get("tools", [])) or "none"
    print(f"\n  [mode: {r['mode']} · tools: {tools}]\n")


def main():
    ap = argparse.ArgumentParser(description="SLA Monitoring Agent")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("report")
    r.add_argument("--send", action="store_true", help="e-mail / webhook the report")
    r.add_argument("--open", action="store_true", help="open the HTML report in the browser")
    a = sub.add_parser("ask")
    a.add_argument("question", nargs="+")
    sub.add_parser("chat")
    sub.add_parser("risk")
    sub.add_parser("doctor")
    args = ap.parse_args()
    cmd = args.cmd or "chat"

    agent = SLAAgent()
    if cmd == "report":
        rep = agent.daily_report(send=args.send)
        print(f"\n{rep['subject']}\n\n{rep['summary']}\n")
        print(f"Saved: {rep['md_path']}\n       {rep['html_path']}")
        if rep["sent"]:
            print("Sent: " + "; ".join(f"{k}: {v}" for k, v in rep["sent"].items()))
        if args.open:
            webbrowser.open(Path(rep["html_path"]).as_uri())
    elif cmd == "ask":
        show(agent.chat(" ".join(args.question)))
    elif cmd == "risk":
        show(agent.chat("Which open tickets are most likely to breach?"))
    elif cmd == "doctor":
        s = agent.settings
        print(f"Mode        : {agent.mode}")
        print(f"Data        : {len(agent.data.df):,} tickets, as of {agent.data.as_of}")
        print(f"E-mail      : {'configured -> ' + s.email_to if s.email_enabled else 'not configured'}")
        print(f"Webhook     : {'configured' if s.webhook_url else 'not configured'}")
        m = agent.get_predictor().metrics
        print(f"ML model    : ROC AUC {m['roc_auc']}, PR AUC {m['pr_auc']} (tested on {m['test_period']})")
        if agent.llm:
            try:
                out = agent.llm.complete([{"role": "user", "content": "Reply with the single word OK."}])
                print("LLM test    : " + (out["choices"][0]["message"].get("content") or "").strip()[:60])
            except Exception as e:
                print(f"LLM test    : FAILED - {e}")
    else:
        print(f"\nSLA Monitoring Agent · mode: {agent.mode}")
        print("Ask anything about SLA performance. Type 'help' for ideas, 'exit' to quit.\n")
        history = []
        while True:
            try:
                q = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q.lower() in ("exit", "quit", "q"):
                break
            if not q:
                continue
            res = agent.chat(q, history)
            show(res)
            history += [{"role": "user", "content": q}, {"role": "assistant", "content": res["answer"]}]


if __name__ == "__main__":
    main()
