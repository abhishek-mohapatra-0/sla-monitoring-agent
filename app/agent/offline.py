"""
Offline mode: answers questions with no LLM at all.

A keyword router picks the right tool, a small parser pulls out team / priority /
agent / period, and templates turn the tool result into a readable answer. It is
less flexible than the LLM but always available, free and instant.
"""
from __future__ import annotations

import calendar
import re

import pandas as pd

from .analysis import pct

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})

HELP = (
    "I can answer questions like:\n"
    "- *How are we doing today?* (daily briefing)\n"
    "- *Why did SLA drop in March?*\n"
    "- *Which tickets will breach next?*\n"
    "- *Which agents need support?* / *Who has a high reopen rate?*\n"
    "- *What is Network Ops P2 SLA last month?*\n"
    "- *Compare August vs July* · *Show the monthly trend for Service Desk*\n"
    "- *Why do night tickets breach?* · *Do reassignments matter?*\n"
    "- *Tell me about INC1059600*"
)


class OfflineResponder:
    def __init__(self, toolbox):
        self.tb = toolbox
        self.data = toolbox.data
        self.as_of = self.data.as_of
        self.agents = sorted(self.data.df.AgentName.unique())

    # ------------------------------------------------------------------ parsing
    def parse(self, q: str) -> dict:
        ql = q.lower()
        ent = {}
        for t in self.data.teams:
            if t.lower() in ql:
                ent["team"] = t
        aliases = {"network": "Network Ops", "app support": "Application Support", "service desk": "Service Desk",
                   "infra": "Infrastructure", "dba": "Database", "security": "Security Ops"}
        if "team" not in ent:
            for k, v in aliases.items():
                if re.search(rf"\b{k}\b", ql):
                    ent["team"] = v
        m = re.search(r"\bp([1-4])\b", ql)
        if m:
            ent["priority"] = f"P{m.group(1)}"
        for a in self.agents:
            first, last = a.lower().split(" ", 1)
            if a.lower() in ql or re.search(rf"\b{last}\b", ql) and re.search(rf"\b{first}\b", ql):
                ent["agent"] = a
        m = re.search(r"\binc\s?(\d{7})\b", ql)
        if m:
            ent["ticket"] = f"INC{m.group(1)}"
        m = re.search(r"next\s+(\d+)\s*(h|hour|hours|hrs)\b", ql)
        if m:
            ent["hours"] = int(m.group(1))
        ent["periods"] = self._periods(ql)
        return ent

    def _month(self, mi: int, year: int | None):
        if year is None:
            year = self.as_of.year if mi <= self.as_of.month else self.as_of.year - 1
        s = pd.Timestamp(year=year, month=mi, day=1)
        e = s + pd.offsets.MonthEnd(0)
        return {"label": s.strftime("%B %Y") + (" (month to date)" if s.to_period("M") == self.as_of.to_period("M") else ""),
                "start": s.strftime("%Y-%m-%d"), "end": min(e, self.as_of.normalize()).strftime("%Y-%m-%d")}

    def _periods(self, ql: str) -> list[dict]:
        out = []
        today = self.as_of.normalize()
        if "this month" in ql or "mtd" in ql:
            out.append(self._month(today.month, today.year))
        if "last month" in ql or "previous month" in ql:
            p = (today - pd.offsets.MonthBegin(1)) - pd.Timedelta(days=1)
            out.append(self._month(p.month, p.year))
        m = re.search(r"last\s+(\d+)\s*(day|days|week|weeks)", ql)
        if m:
            n = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
            out.append({"label": f"last {n} days", "start": (today - pd.Timedelta(days=n - 1)).strftime("%Y-%m-%d"),
                        "end": today.strftime("%Y-%m-%d")})
        elif re.search(r"\blast week\b", ql):
            out.append({"label": "last 7 days", "start": (today - pd.Timedelta(days=6)).strftime("%Y-%m-%d"),
                        "end": today.strftime("%Y-%m-%d")})
        for m in re.finditer(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\s+'?(\d{2,4}))?", ql):
            word = m.group(1)
            if word == "may" and not re.search(r"\bmay\s+('?\d{2,4}|vs|and|,)|\bin may\b|\bmay\b\s*$", ql):
                continue                      # "may" is usually the verb
            if word in ("mar", "jun", "sep", "oct", "dec", "jan", "feb", "apr", "jul", "aug", "nov") \
                    and word not in ql.split():
                continue
            y = m.group(2)
            year = int(y) + (2000 if len(y) == 2 else 0) if y and y.isdigit() else None
            per = self._month(MONTHS[word], year)
            if per not in out:
                out.append(per)
        return out

    # ------------------------------------------------------------------ routing
    def answer(self, q: str) -> dict:
        ql = q.lower().strip()
        e = self.parse(q)
        per = e["periods"][0] if e["periods"] else None
        flt = {k: e[k] for k in ("team", "priority", "agent") if k in e}
        if per:
            flt.update(start=per["start"], end=per["end"])

        def has(*words):
            return any(re.search(rf"\b{w}", ql) for w in words)

        if not ql or has("help", "what can you", "hello", "hi$", "hey"):
            return self._r(HELP, [])
        if "ticket" in e:
            return self._r(self.fmt_ticket(self.tb.get_ticket(e["ticket"])), ["get_ticket"])
        if has("predict", "risk", "about to breach", "will breach", "going to breach", "likely to breach", "next \\d+"):
            res = self.tb.predict_breach_risk(limit=10, team=e.get("team"), priority=e.get("priority"))
            txt = self.fmt_risk(res)
            tools = ["predict_breach_risk"]
            if "hours" in e:
                qd = self.tb.open_queue(within_hours=e["hours"], team=e.get("team"), priority=e.get("priority"))
                txt = self.fmt_queue(qd, f"Due within {e['hours']} hours") + "\n\n" + txt
                tools.append("open_queue")
            return self._r(txt, tools)
        if has("overdue", "queue", "backlog", "open ticket", "breached tickets", "to action"):
            qd = self.tb.open_queue(team=e.get("team"), priority=e.get("priority"),
                                    within_hours=e.get("hours"))
            return self._r(self.fmt_queue(qd, "Open tickets (most urgent first)"), ["open_queue"])
        if has("reopen"):
            return self._r(self.fmt_reopen(self.tb.find_outliers("reopen", e.get("team"))), ["find_outliers"])
        if has("night", "weekend", "hour", "shift", "time of day", "response sla", "first response"):
            return self._r(self.fmt_time(self.tb.find_outliers("time", e.get("team"))), ["find_outliers"])
        if has("reassign", "hand-off", "handoff", "hand off", "bounce", "hop"):
            return self._r(self.fmt_reassign(self.tb.find_outliers("reassignment", e.get("team"))), ["find_outliers"])
        if has("why", "cause", "reason", "root", "driver", "drop", "dip", "explain", "fell", "worse"):
            return self._why(e, flt, per)
        if "agent" in e:
            k = self.tb.get_kpis(agent=e["agent"], **{x: flt[x] for x in ("start", "end") if x in flt})
            return self._r(self.fmt_kpis(k, f"{e['agent']}" + (f" · {per['label']}" if per else "")), ["get_kpis"])
        if has("agent", "who", "people", "coach", "worst", "best", "performer", "staff", "support\\?"):
            res = self.tb.find_outliers("agents", e.get("team"))
            res.update(self.tb.find_outliers("reopen", e.get("team")))
            return self._r(self.fmt_agents(res), ["find_outliers"])
        if has("compare", " vs", "versus") and len(e["periods"]) >= 2:
            a, b = e["periods"][:2]
            res = self.tb.compare_periods(a["start"], a["end"], b["start"], b["end"],
                                          team=e.get("team"), priority=e.get("priority"))
            return self._r(self.fmt_compare(res, a["label"], b["label"]), ["compare_periods"])
        if has("trend", "month by month", "over time", "monthly", "history", "compare"):
            res = self.tb.monthly_trend(team=e.get("team"), priority=e.get("priority"))
            return self._r(self.fmt_trend(res, e), ["monthly_trend"])
        if has("summary", "status", "health", "brief", "report", "how are we", "how is", "overall", "today", "doing"):
            return self._r(self.fmt_health(self.tb.health_check()), ["health_check"])
        if flt or has("sla", "kpi", "mttr", "csat", "how many", "what is", "breach"):
            k = self.tb.get_kpis(**{x: v for x, v in flt.items() if x != "agent"})
            title = " · ".join([x for x in [e.get("team"), e.get("priority"), per["label"] if per else "all data"] if x])
            return self._r(self.fmt_kpis(k, title), ["get_kpis"])
        return self._r("I'm not sure what you mean yet.\n\n" + HELP, [])

    def _why(self, e, flt, per):
        rc = self.tb.root_cause(**flt)
        scope = " · ".join([x for x in [e.get("agent"), e.get("team"), e.get("priority"),
                                         per["label"] if per else "all data"] if x])
        lines = [f"**Why are we breaching? ({scope})**", "",
                 f"{rc['breaches']:,} resolution breaches out of {rc['measured']:,} measured tickets "
                 f"({pct(rc['breach_rate'])} breach rate)."]
        tools = ["root_cause"]
        if per and per["start"][8:] == "01":
            s = pd.Timestamp(per["start"])
            ps = s - pd.offsets.MonthBegin(1)
            pe = s - pd.Timedelta(days=1)
            cmp = self.tb.compare_periods(per["start"], per["end"], ps.strftime("%Y-%m-%d"), pe.strftime("%Y-%m-%d"),
                                          team=e.get("team"), priority=e.get("priority"))
            ka, kb = list(cmp.values())[:2]
            if ka["res_sla"] is not None and kb["res_sla"] is not None:
                lines.append(f"Resolution SLA was **{pct(ka['res_sla'])}** vs {pct(kb['res_sla'])} the month before "
                             f"({(ka['res_sla'] - kb['res_sla']) * 100:+.1f} pts), on {ka['total']:,} tickets vs {kb['total']:,}.")
            tools.append("compare_periods")
            vol = [v for v in self.tb.find_outliers("volume")["volume_anomalies"] if v["month"] == per["start"][:7]]
            if vol:
                v = vol[0]
                lines.append(f"Volume spiked to {v['tickets']:,} tickets (typical {v['typical_tickets']:,}), "
                             f"led by **{v['surging_subcategory']}** ({pct(v['surging_share'])} of the month).")
                tools.append("find_outliers")
        if rc["path"]:
            lines += ["", "**Drill-down (biggest excess breaches at each level):**"]
            for i, p in enumerate(rc["path"], 1):
                lines.append(f"{i}. {p['dimension']} = **{p['value']}**: {pct(p['breach_rate'])} breach rate "
                             f"({p['lift']}× the level above), {p['breaches']:,} breaches, "
                             f"{pct(p['share_of_all_breaches'])} of all breaches")
        if rc["drivers"]:
            lines += ["", "**Other big drivers:** " + "; ".join(
                f"{d['dimension']} {d['value']} ({pct(d['breach_rate'])}, +{d['excess_breaches']:,} excess)"
                for d in rc["drivers"][:4])]
        lines += ["", "**Suggested actions:** " + self.actions_for(rc)]
        return self._r("\n".join(lines), tools)

    @staticmethod
    def actions_for(rc) -> str:
        acts = []
        for p in rc["path"]:
            d, v = p["dimension"], p["value"]
            if d == "Reassignments":
                acts.append("fix routing so tickets reach the right resolver group first time (assignment rules / skills-based routing)")
            elif d == "SubCategory":
                acts.append(f"add surge capacity or a dedicated squad for {v} tickets, and publish a known-error article")
            elif d == "Agent":
                acts.append(f"review {v}'s workload and coach on the slowest ticket types")
            elif d == "Team":
                acts.append(f"daily breach review with the {v} lead")
            elif d == "Priority":
                acts.append(f"escalation alerts for {v} tickets at 50% and 75% of SLA time")
            elif d == "Shift":
                acts.append(f"cover the {v.lower()} shift (on-call or auto-acknowledgement)")
            elif d == "Weekday":
                acts.append(f"re-balance the roster for {v}")
        return "; ".join(dict.fromkeys(acts)) or "keep monitoring - no single segment stands out."

    @staticmethod
    def _r(text, tools):
        return {"answer": text, "tools": [{"tool": t} for t in tools]}

    # ------------------------------------------------------------------ formatters
    @staticmethod
    def fmt_kpis(k, title):
        if not k.get("total"):
            return f"No tickets match **{title}**."
        stat = {"On target": "▲ On target", "Watch": "● Watch", "Below target": "▼ Below target"}.get(k["status"], "")
        return "\n".join([
            f"**{title}**", "",
            "| Metric | Value |", "|---|---|",
            f"| Resolution SLA | **{pct(k['res_sla'])}** vs target {pct(k['target'])} ({stat}, {k['gap_pts']:+.1f} pts) |"
            if k["res_sla"] is not None else "| Resolution SLA | n/a |",
            f"| Response SLA | {pct(k['resp_sla'])} |",
            f"| Tickets | {k['total']:,} ({k['breaches']:,} resolution breaches) |",
            f"| Open now | {k['open']} ({k['overdue']} overdue, {k['at_risk']} at risk) |",
            f"| MTTR / MTTA | {k['mttr_hrs']} h / {k['mtta_min']} min |",
            f"| CSAT · Reopen rate | {k['csat']} · {pct(k['reopen_rate'])} |",
        ])

    @staticmethod
    def fmt_ticket(t):
        if "error" in t:
            return t["error"]
        tl = "\n".join(f"- {x['step']}: {x['at'] or '—'}" + ("" if x.get("ok") is None else (" ✓" if x["ok"] else " ✗ late"))
                       for x in t["timeline"])
        htb = "" if t["hours_to_breach"] is None else f" · hours to breach **{t['hours_to_breach']}**"
        return (f"**{t['id']}** · {t['priority']} · {t['team']} · {t['agent']}\n\n"
                f"{t['category']} / {t['sub']} via {t['channel']} · status **{t['status']}** ({t['sla']}){htb}\n\n"
                f"Reassignments {t['reassign']} · reopened {'yes' if t['reopened'] else 'no'} · "
                f"CSAT {t['csat'] if t['csat'] is not None else '—'}\n\n{tl}")

    @staticmethod
    def fmt_risk(res):
        m = res["model"]
        rows = ["| Ticket | Pri | Team | Agent | Hours left | Risk | Why |", "|---|---|---|---|---|---|---|"]
        for t in res["tickets"]:
            rows.append(f"| {t['ticket']} | {t['priority']} | {t['team']} | {t['agent']} | {t['hours_to_breach']} | "
                        f"**{pct(t['breach_risk'], 0)}** | {'; '.join(t['why']) or '—'} |")
        return (f"**Open tickets most likely to breach** (ML model, ROC AUC {m['roc_auc']} on {m['test_period']})\n\n"
                + "\n".join(rows) + "\n\n*Action:* reassign or swarm the top tickets before they cross their due time.")

    @staticmethod
    def fmt_queue(q, title):
        rows = ["| Ticket | Pri | Team | Agent | Status | Hours to breach |", "|---|---|---|---|---|---|"]
        for t in q["tickets"]:
            rows.append(f"| {t['ticket']} | {t['priority']} | {t['team']} | {t['agent']} | {t['status']} | {t['hours_to_breach']} |")
        return f"**{title}**: {q['count']} tickets, {q['overdue']} already overdue.\n\n" + "\n".join(rows)

    @staticmethod
    def fmt_agents(res):
        out = ["**Agents who need support**", ""]
        for a in res.get("slow_agents", []):
            out.append(f"- **{a['agent']}** ({a['team']}): {pct(a['res_sla'])} resolution SLA vs {pct(a['peer_res_sla'])} for "
                       f"team peers ({a['gap_pts']:+.1f} pts); MTTR {a['mttr_hrs']} h vs {a['peer_mttr_hrs']} h.")
        for a in res.get("high_reopen_agents", []):
            out.append(f"- **{a['agent']}** ({a['team']}): reopen rate {pct(a['reopen_rate'])} vs {pct(a['overall_reopen_rate'])} overall"
                       + (f"; new joiner ({a['tenure_months']} months)" if a["new_joiner"] else "") + ".")
        if len(out) == 2:
            out.append("No agent stands out from their peers.")
        out += ["", "*Suggested:* workload review and 1:1 coaching for slow resolvers; QA checks on closures and a buddy for new joiners."]
        return "\n".join(out)

    @staticmethod
    def fmt_reopen(res):
        rows = res.get("high_reopen_agents", [])
        if not rows:
            return "No agent has an unusually high reopen rate."
        return "**High reopen rates**\n\n" + "\n".join(
            f"- **{a['agent']}** ({a['team']}): {pct(a['reopen_rate'])} of {a['resolved']:,} resolved tickets reopened "
            f"(overall {pct(a['overall_reopen_rate'])}); tenure {a['tenure_months']} months"
            + (" - new joiner, likely needs coaching and a closure checklist." if a["new_joiner"] else ".") for a in rows)

    @staticmethod
    def fmt_time(res):
        rows = res.get("time_patterns", [])
        if not rows:
            return "No time-of-day or weekend pattern stands out."
        return "**When do we miss the first-response SLA?**\n\n" + "\n".join(
            f"- **{t['pattern']}**: {pct(t['response_breach_rate'])} response breach rate "
            f"(vs {pct(t.get('overall_response_breach_rate') or t.get('weekday_response_breach_rate'))}"
            f"{' overall' if t.get('overall_response_breach_rate') is not None else ' on weekdays'}). {t.get('hint') or ''}"
            for t in rows) + "\n\n*Suggested:* night on-call or auto-acknowledgement for P3/P4, and more weekend cover."

    @staticmethod
    def fmt_reassign(res):
        r = res["reassignment"]
        rows = "\n".join(f"- {b['handoffs']} hand-off{'' if b['handoffs'] == '1' else 's'}: {pct(b['breach_rate'])} breach rate ({b['tickets']:,} tickets)"
                         for b in r["bands"])
        t = r["most_reassigned_team"]
        return (f"**Reassignments vs breaches**\n\n{rows}\n\nMost reassigned team: **{t['team']}** "
                f"({pct(t['multi_hop_share'])} of its tickets hop 2+ times).\n\n"
                "*Suggested:* better categorisation at logging and skills-based routing to cut hand-offs.")

    @staticmethod
    def fmt_trend(res, e):
        rows = ["| Month | Tickets | Resolution SLA | Target | Breaches |", "|---|---|---|---|---|"]
        for m in res["months"]:
            rows.append(f"| {m['month']}{' (MTD)' if m['partial'] else ''} | {m['tickets']:,} | {pct(m['res_sla'])} | "
                        f"{pct(m['target'])} | {m['breaches']:,} |")
        scope = " · ".join([x for x in [e.get("team"), e.get("priority")] if x]) or "all teams"
        valid = [m for m in res["months"] if m["res_sla"] is not None]
        worst = min(valid, key=lambda m: m["res_sla"]) if valid else None
        note = f"\n\nLowest month: **{worst['month']}** at {pct(worst['res_sla'])}." if worst else ""
        return f"**Monthly trend ({scope})**\n\n" + "\n".join(rows) + note

    @staticmethod
    def fmt_compare(res, la, lb):
        ka, kb = list(res.values())[:2]
        d = res["delta"]
        return "\n".join([
            f"**{la} vs {lb}**", "",
            f"| Metric | {la} | {lb} | Change |", "|---|---|---|---|",
            f"| Resolution SLA | {pct(ka['res_sla'])} | {pct(kb['res_sla'])} | {d.get('res_sla_pts', 0):+.1f} pts |",
            f"| Response SLA | {pct(ka['resp_sla'])} | {pct(kb['resp_sla'])} | {d.get('resp_sla_pts', 0):+.1f} pts |",
            f"| Tickets | {ka['total']:,} | {kb['total']:,} | {d.get('total', 0):+,.0f} |",
            f"| Breaches | {ka['breaches']:,} | {kb['breaches']:,} | {d.get('breaches', 0):+,.0f} |",
            f"| MTTR (h) | {ka['mttr_hrs']} | {kb['mttr_hrs']} | {d.get('mttr_hrs', 0):+.1f} |",
            f"| CSAT | {ka['csat']} | {kb['csat']} | {d.get('csat', 0):+.2f} |",
        ])

    @staticmethod
    def fmt_health(h):
        c = h["current"]
        icon = {"critical": "🔴", "warning": "🟠", "info": "🔵", "ok": "🟢"}
        lines = [f"**SLA briefing · as of {h['as_of']}**", "",
                 f"Last {h['window']['days']} days: resolution SLA **{pct(c['res_sla'])}** vs target {pct(c['target'])} "
                 f"(**{c['status']}**, {c['gap_pts']:+.1f} pts) · {c['total']:,} tickets · {c['open']} open, "
                 f"{c['overdue']} overdue.", "",
                 f"**{h['counts']['critical']} critical · {h['counts']['warning']} warnings · {h['counts']['info']} info**", ""]
        for a in h["alerts"]:
            lines.append(f"- {icon[a['severity']]} **{a['title']}**: {a['detail']}")
        rc = h["root_cause"]["path"]
        if rc:
            lines += ["", "**Root cause (last 30 days):** " + " → ".join(f"{p['dimension']} = {p['value']} ({pct(p['breach_rate'])})" for p in rc)]
        risk = (h.get("at_risk_tickets") or {}).get("tickets") or []
        if risk:
            lines += ["", "**Highest breach risk now:** " + ", ".join(f"{t['ticket']} ({pct(t['breach_risk'], 0)})" for t in risk[:5])]
        return "\n".join(lines)
