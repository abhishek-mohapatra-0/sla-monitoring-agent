"""
SLAAgent: the brain that ties everything together.

    agent = SLAAgent()
    agent.chat("Why did SLA drop in March?")      -> answer + tools used
    agent.briefing()                              -> today's health check (dict)
    agent.daily_report(send=True)                 -> writes reports/, emails / posts it
"""
from __future__ import annotations

import json
import threading

from metrics import SLAData

from .analysis import Analyst
from .config import get_settings
from .llm import LLMClient, LLMError
from .offline import OfflineResponder
from .tools import Toolbox

SYSTEM_PROMPT = """You are the SLA Monitoring Agent for an IT service desk.
You help service-delivery managers understand SLA performance, find root causes of breaches
and decide what to do next.

Facts about the data:
- Current date/time (data snapshot): {as_of}. "Today" means this date.
- Tickets created {min_date} to {max_date}. Months with no year mean the most recent one
  that is not after {as_of_month} (e.g. "March" = 2026-03, "September" = 2026-09 month-to-date).
- "This month" = {this_month_start} to {as_of_date}. "Last month" = {last_month_start} to {last_month_end}.
- Teams: {teams}. Priorities: P1 (4h, 98% target), P2 (8h, 95%), P3 (24h, 92%), P4 (72h, 90%).
  Channels: {channels}.
- Resolution SLA % = tickets resolved within SLA / tickets with a known outcome. The overall target
  is weighted by the priority mix.

Rules:
1. ALWAYS call tools to get numbers. Never invent or estimate figures.
2. For "why" questions call root_cause (with the right dates / team) and, when it helps,
   compare_periods or find_outliers. For "which tickets will breach" call predict_breach_risk.
3. Answer in concise Markdown: a one-line headline with the key number, 2-5 bullets of evidence,
   then "Recommended actions" with 1-3 concrete steps. Use tables only for lists of tickets or months.
4. Show percentages with one decimal (e.g. 88.9%) and say "pts" for percentage-point gaps.
5. If a name is ambiguous or unknown, call list_values and use the closest valid value.
"""


class SLAAgent:
    def __init__(self, data: SLAData | None = None):
        self.settings = get_settings()
        self.data = data or SLAData()
        self.analyst = Analyst(self.data)
        self._predictor = None
        self._lock = threading.Lock()
        self.tools = Toolbox(self.data, self.analyst, self.get_predictor)
        self.offline = OfflineResponder(self.tools)
        s = self.settings
        self.llm = LLMClient(s.base_url, s.model, s.api_key) if s.llm_enabled else None

    # ------------------------------------------------------------------ lazy ML model
    def get_predictor(self):
        with self._lock:
            if self._predictor is None:
                from .predictor import BreachPredictor
                self._predictor = BreachPredictor(self.data)
            return self._predictor

    @property
    def mode(self) -> str:
        return self.settings.label

    def system_prompt(self) -> str:
        import pandas as pd
        a = self.data.as_of
        lm_end = a.normalize().replace(day=1) - pd.Timedelta(days=1)
        return SYSTEM_PROMPT.format(
            as_of=a.strftime("%Y-%m-%d %H:%M (%A)"), as_of_date=a.strftime("%Y-%m-%d"),
            as_of_month=a.strftime("%Y-%m"),
            min_date=self.data.min_date.strftime("%Y-%m-%d"), max_date=self.data.max_date.strftime("%Y-%m-%d"),
            this_month_start=a.strftime("%Y-%m-01"),
            last_month_start=lm_end.strftime("%Y-%m-01"), last_month_end=lm_end.strftime("%Y-%m-%d"),
            teams=", ".join(self.data.teams), channels=", ".join(self.data.channels))

    # ------------------------------------------------------------------ chat
    def chat(self, message: str, history: list[dict] | None = None) -> dict:
        message = (message or "").strip()
        if self.llm is None:
            r = self.offline.answer(message)
            return {**r, "mode": "offline"}
        msgs = [{"role": "system", "content": self.system_prompt()}]
        for h in (history or [])[-8:]:                 # short memory of the conversation
            if h.get("role") in ("user", "assistant") and h.get("content"):
                msgs.append({"role": h["role"], "content": str(h["content"])[:4000]})
        msgs.append({"role": "user", "content": message})
        try:
            answer, trace = self.llm.run_tools(msgs, self.tools.specs, self.tools.call)
            if not answer:
                raise LLMError("empty answer")
            return {"answer": answer, "tools": trace, "mode": self.mode}
        except LLMError as e:
            r = self.offline.answer(message)
            r["answer"] += f"\n\n<sub>LLM unavailable ({str(e)[:120]}), answered in offline mode.</sub>"
            return {**r, "mode": "offline (fallback)"}

    # ------------------------------------------------------------------ briefing & report
    def briefing(self) -> dict:
        return self.analyst.health_check(window_days=self.settings.report_window_days,
                                         predictor=self.get_predictor())

    def executive_summary(self, h: dict) -> tuple[str, str]:
        """(markdown summary, who wrote it). LLM if available, template otherwise."""
        if self.llm is not None:
            compact = {k: h[k] for k in ("as_of", "window", "current", "previous", "status", "counts", "alerts")}
            compact["root_cause_path"] = h["root_cause"]["path"]
            compact["top_risk"] = (h.get("at_risk_tickets") or {}).get("tickets", [])[:5]
            prompt = ("Write the executive summary of today's SLA report for a service-delivery manager. "
                      "Use ONLY the JSON facts below. Format: a bold one-line headline, then 4-6 short bullets "
                      "(status vs target, biggest problem and its root cause, people/process patterns, what is at "
                      "risk today), then 'Recommended actions' with 3 numbered, specific actions. Max 180 words.\n\n"
                      + json.dumps(compact, default=str))
            try:
                r = self.llm.complete([{"role": "system", "content": "You are a precise SLA analyst."},
                                       {"role": "user", "content": prompt}], temperature=0.3)
                txt = (r["choices"][0]["message"].get("content") or "").strip()
                if txt:
                    return txt, self.mode
            except LLMError:
                pass
        return self.template_summary(h), "offline template"

    def template_summary(self, h: dict) -> str:
        from .analysis import pct
        c, p = h["current"], h["previous"]
        crit = [a for a in h["alerts"] if a["severity"] == "critical"]
        warn = [a for a in h["alerts"] if a["severity"] == "warning"]
        rc = h["root_cause"]["path"]
        lines = [f"**Resolution SLA is {pct(c['res_sla'])} against a {pct(c['target'])} target "
                 f"({c['status']}, {c['gap_pts']:+.1f} pts) over the last {h['window']['days']} days.**", ""]
        lines.append(f"- Versus the previous {h['baseline']['days']} days: {pct(p['res_sla'])} "
                     f"({(c['res_sla'] - p['res_sla']) * 100:+.1f} pts); {c['breaches']} resolution breaches on {c['total']:,} tickets.")
        if rc:
            lines.append("- Main driver: " + " → ".join(f"{x['dimension']} {x['value']} ({pct(x['breach_rate'])} breach rate)" for x in rc) + ".")
        for a in crit[:2]:
            lines.append(f"- {a['title']}. {a['detail']}")
        people = [a for a in warn if a["metric"] in ("agent", "reopen")]
        if people:
            lines.append("- People: " + "; ".join(a["title"] for a in people) + ".")
        risk = (h.get("at_risk_tickets") or {}).get("tickets") or []
        if risk:
            lines.append(f"- {len(risk)} open tickets have a high predicted breach risk, led by "
                         + ", ".join(f"{t['ticket']} ({pct(t['breach_risk'], 0)})" for t in risk[:3]) + ".")
        acts = [OfflineResponder.actions_for(h["root_cause"])]
        if any(a["metric"] == "overdue" for a in crit):
            acts.insert(0, "escalate the overdue tickets to team leads today")
        if people:
            acts.append("1:1 coaching and QA review for the flagged agents")
        lines += ["", "**Recommended actions**"] + [f"{i}. {a[0].upper() + a[1:]}." for i, a in enumerate(acts[:3], 1)]
        return "\n".join(lines)

    def daily_report(self, send: bool = False) -> dict:
        from .notify import notify
        from .report import build_report
        h = self.briefing()
        summary, author = self.executive_summary(h)
        rep = build_report(h, summary, author, self.get_predictor().metrics)
        sent = notify(self.settings, rep) if send else {}
        return {**rep, "sent": sent, "status": h["status"], "counts": h["counts"]}
