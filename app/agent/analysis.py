"""
Deterministic analytics the agent relies on.

Everything here is plain pandas, so the numbers are exact and repeatable. The LLM
only *explains* these results; it never calculates anything itself.

  health_check()   daily SLA check -> list of alerts with severity
  root_cause()     automatic decomposition-tree drill-down (largest "excess breaches")
  drivers()        top contributors per dimension
  outliers()       agent SLA, reopen rate, time-of-day, weekend, volume surges
  monthly_trend()  month-by-month SLA and volume
  compare()        KPIs of two periods side by side
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from metrics import BREAKDOWN_DIMS, SLAData, _f

# Category duplicates Team 1:1 in this dataset, so it is left out of the drill-down.
DRILL_DIMS = ["Team", "Priority", "SubCategory", "Reassignments", "Shift", "Channel", "Weekday", "Agent"]
KPI_KEYS = ["total", "res_sla", "target", "gap_pts", "status", "resp_sla", "breaches",
            "resp_breaches", "open", "overdue", "at_risk", "mttr_hrs", "mtta_min",
            "csat", "reopen_rate", "multi_hop"]


def slim(k: dict) -> dict:
    return {x: k.get(x) for x in KPI_KEYS}


def pct(x, nd=1):
    return "n/a" if x is None or pd.isna(x) else f"{x * 100:.{nd}f}%"


class Analyst:
    def __init__(self, data: SLAData):
        self.data = data
        self.df = data.df
        self.as_of = data.as_of

    # ------------------------------------------------------------------ helpers
    def frame(self, start=None, end=None, team=None, priority=None, channel=None, agent=None):
        d = self.data.filter(start=start, end=end, team=team, priority=priority, channel=channel)
        if agent:
            d = d[d.AgentName.str.lower() == str(agent).lower()]
        return d

    def window(self, days: int, offset_days: int = 0):
        end = self.as_of.normalize() - pd.Timedelta(days=offset_days)
        start = end - pd.Timedelta(days=days - 1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    # ------------------------------------------------------------------ KPIs
    def kpis(self, **flt) -> dict:
        d = self.frame(**flt)
        return {"filters": {k: v for k, v in flt.items() if v}, **slim(self.data.kpis(d))}

    def compare(self, a: dict, b: dict, label_a="current", label_b="previous", **common) -> dict:
        ka = self.kpis(**{**common, **a})
        kb = self.kpis(**{**common, **b})
        delta = {}
        for k in ("res_sla", "resp_sla", "reopen_rate", "multi_hop"):
            if ka.get(k) is not None and kb.get(k) is not None:
                delta[k + "_pts"] = round((ka[k] - kb[k]) * 100, 2)
        for k in ("total", "breaches", "mttr_hrs", "csat"):
            if ka.get(k) is not None and kb.get(k) is not None:
                delta[k] = round(ka[k] - kb[k], 2)
        return {label_a: ka, label_b: kb, "delta": delta}

    def monthly_trend(self, **flt) -> list[dict]:
        d = self.frame(**{**flt, "start": None, "end": None})
        out = []
        for m, g in d.groupby("Month"):
            k = self.data.kpis(g)
            out.append({"month": str(m), "tickets": k["total"], "res_sla": k["res_sla"],
                        "target": k["target"], "breaches": k["breaches"], "resp_sla": k["resp_sla"],
                        "mttr_hrs": k["mttr_hrs"], "partial": bool(m == self.as_of.to_period("M"))})
        return out

    # ------------------------------------------------------------------ root cause
    @staticmethod
    def _split(m: pd.DataFrame, dim: str, base_rate: float, min_n: int):
        col = BREAKDOWN_DIMS[dim]
        g = m.groupby(col, observed=True).agg(n=("TicketID", "size"),
                                             b=("ResolutionSLAMet", lambda x: int((x == 0).sum())))
        g = g[g.n >= min_n]
        if g.empty:
            return []
        g["rate"] = g.b / g.n
        g["excess"] = g.b - g.n * base_rate
        g["lift"] = g.rate / base_rate if base_rate else np.nan
        g = g.sort_values("excess", ascending=False)
        return [{"dimension": dim, "value": str(i), "tickets": int(r.n), "breaches": int(r.b),
                 "breach_rate": _f(r.rate), "lift": _f(r.lift, 2), "excess_breaches": int(round(r.excess))}
                for i, r in g.iterrows()]

    def drivers(self, top=8, min_n=150, **flt) -> dict:
        """Best (highest excess-breach) value in every dimension, ranked."""
        m = self.frame(**flt)
        m = m[m.ResolutionSLAMet.notna()]
        if m.empty:
            return {"breaches": 0, "measured": 0, "breach_rate": None, "drivers": []}
        base = float((m.ResolutionSLAMet == 0).mean())
        best = []
        for dim in DRILL_DIMS:
            rows = self._split(m, dim, base, min_n)
            best += [r for r in rows[:2] if r["excess_breaches"] > 0 and (r["lift"] or 0) >= 1.15]
        best.sort(key=lambda r: -r["excess_breaches"])
        return {"breaches": int((m.ResolutionSLAMet == 0).sum()), "measured": int(len(m)),
                "breach_rate": _f(base), "drivers": best[:top]}

    def root_cause(self, depth=3, min_n=100, **flt) -> dict:
        """Greedy decomposition tree: at each level pick the split that explains the
        most excess breaches, then drill into it (like Power BI's 'High value' split)."""
        m = self.frame(**flt)
        m = m[m.ResolutionSLAMet.notna()]
        overall = float((m.ResolutionSLAMet == 0).mean()) if len(m) else None
        path, used, node = [], set(), m
        for _ in range(depth):
            if node.empty:
                break
            base = float((node.ResolutionSLAMet == 0).mean())
            cands = []
            for dim in DRILL_DIMS:
                if dim in used:
                    continue
                n_min = max(30, min(min_n, int(0.05 * len(node))))
                rows = self._split(node, dim, base, n_min)
                if rows and rows[0]["excess_breaches"] > 0 and (rows[0]["lift"] or 0) >= 1.15:
                    cands.append(rows[0])
            if not cands:
                break
            best = max(cands, key=lambda r: r["excess_breaches"])
            best["parent_breach_rate"] = _f(base)
            path.append(best)
            used.add(best["dimension"])
            node = node[node[BREAKDOWN_DIMS[best["dimension"]]].astype(str) == best["value"]]
        total_b = int((m.ResolutionSLAMet == 0).sum())
        for p in path:
            p["share_of_all_breaches"] = _f(p["breaches"] / total_b) if total_b else None
        return {"filters": {k: v for k, v in flt.items() if v}, "measured": int(len(m)),
                "breaches": total_b, "breach_rate": _f(overall), "path": path,
                "drivers": self.drivers(**flt)["drivers"][:6]}

    # ------------------------------------------------------------------ outliers
    def agent_outliers(self, min_n=300, gap_pts=-8.0, **flt) -> list[dict]:
        d = self.frame(**flt)
        m = d[d.ResolutionSLAMet.notna()]
        out = []
        for (team, agent), g in m.groupby(["Team", "AgentName"]):
            if len(g) < min_n:
                continue
            peers = m[(m.Team == team) & (m.AgentName != agent)]
            a, p = g.ResolutionSLAMet.mean(), peers.ResolutionSLAMet.mean()
            gap = (a - p) * 100
            if gap <= gap_pts:
                out.append({"agent": agent, "team": team, "tickets": int(len(g)),
                            "res_sla": _f(a), "peer_res_sla": _f(p), "gap_pts": round(gap, 1),
                            "mttr_hrs": _f(g.ResolutionHours.mean(), 1),
                            "peer_mttr_hrs": _f(peers.ResolutionHours.mean(), 1)})
        return sorted(out, key=lambda r: r["gap_pts"])

    def reopen_outliers(self, min_n=150, factor=2.0, **flt) -> list[dict]:
        d = self.frame(**flt)
        r = d[d.IsOpen == 0]
        overall = r.Reopened.mean()
        hire = self.df.drop_duplicates("AgentName").set_index("AgentName")["HireDate"]
        out = []
        for (team, agent), g in r.groupby(["Team", "AgentName"]):
            if len(g) < min_n:
                continue
            rate = g.Reopened.mean()
            if rate >= overall * factor and rate >= 0.08:
                months = (self.as_of - hire[agent]).days / 30.4
                out.append({"agent": agent, "team": team, "resolved": int(len(g)),
                            "reopen_rate": _f(rate), "overall_reopen_rate": _f(overall),
                            "tenure_months": round(months, 1), "new_joiner": bool(months < 6)})
        return sorted(out, key=lambda r: -r["reopen_rate"])

    def time_outliers(self, **flt) -> list[dict]:
        d = self.frame(**flt)
        r = d[d.ResponseSLAMet.notna()]
        out = []
        base = 1 - r.ResponseSLAMet.mean()
        g = r.groupby(["Shift", "PriorityShort"]).agg(n=("TicketID", "size"), met=("ResponseSLAMet", "mean"))
        for (shift, pr), row in g.iterrows():
            rate = 1 - row.met
            if row.n >= 200 and rate >= max(2 * base, 0.25):
                out.append({"pattern": f"{shift}-shift {pr} tickets", "tickets": int(row.n),
                            "response_breach_rate": _f(rate), "overall_response_breach_rate": _f(base),
                            "hint": "Tickets logged 20:00-08:00 wait for the day shift" if shift == "Night" else None})
        wk = r.assign(weekend=r.DayNo >= 5).groupby("weekend").ResponseSLAMet.mean()
        if True in wk.index and False in wk.index and (wk[False] - wk[True]) >= 0.05:
            out.append({"pattern": "Weekend tickets", "tickets": int((r.DayNo >= 5).sum()),
                        "response_breach_rate": _f(1 - wk[True]),
                        "weekday_response_breach_rate": _f(1 - wk[False]),
                        "hint": "Lower weekend staffing"})
        return sorted(out, key=lambda r: -r["response_breach_rate"])

    def reassignment_effect(self, **flt) -> dict:
        d = self.frame(**flt)
        m = d[d.ResolutionSLAMet.notna()]
        bands = []
        for b in ["0", "1", "2", "3+"]:
            g = m[m.ReassignBand == b]
            bands.append({"handoffs": b, "tickets": int(len(g)),
                          "breach_rate": _f((g.ResolutionSLAMet == 0).mean()) if len(g) else None})
        worst_team = None
        mh = m.assign(h=m.ReassignmentCount >= 2).groupby("Team").h.mean().sort_values(ascending=False)
        if len(mh):
            worst_team = {"team": mh.index[0], "multi_hop_share": _f(mh.iloc[0])}
        return {"bands": bands, "most_reassigned_team": worst_team}

    def volume_anomalies(self, z=2.0, **flt) -> list[dict]:
        d = self.frame(**{**flt, "start": None, "end": None})
        g = d.groupby("Month").agg(n=("TicketID", "size"), sla=("ResolutionSLAMet", "mean"))
        g = g[g.index != self.as_of.to_period("M")]           # skip the partial month
        if len(g) < 4:
            return []
        out = []
        for mth, row in g.iterrows():
            rest = g.drop(mth)
            zs = (row.n - rest.n.mean()) / (rest.n.std() or 1)
            sla_drop = (rest.sla.mean() - row.sla) * 100
            if zs >= z or sla_drop >= 5:
                cur = d[d.Month == mth]
                other = d[d.Month != mth]
                share = cur.SubCategory.value_counts(normalize=True)
                base_share = other.SubCategory.value_counts(normalize=True)
                lift = (share - base_share.reindex(share.index).fillna(0)).sort_values(ascending=False)
                out.append({"month": str(mth), "tickets": int(row.n),
                            "typical_tickets": int(rest.n.mean()), "volume_z": round(float(zs), 1),
                            "res_sla": _f(row.sla), "typical_res_sla": _f(rest.sla.mean()),
                            "sla_drop_pts": round(float(sla_drop), 1),
                            "surging_subcategory": lift.index[0],
                            "surging_share": _f(share[lift.index[0]])})
        return out

    def outliers(self, kind="all", **flt) -> dict:
        res = {}
        if kind in ("all", "agents"):
            res["slow_agents"] = self.agent_outliers(**flt)
        if kind in ("all", "reopen"):
            res["high_reopen_agents"] = self.reopen_outliers(**flt)
        if kind in ("all", "time"):
            res["time_patterns"] = self.time_outliers(**flt)
        if kind in ("all", "reassignment"):
            res["reassignment"] = self.reassignment_effect(**flt)
        if kind in ("all", "volume"):
            res["volume_anomalies"] = self.volume_anomalies(**flt)
        return res

    # ------------------------------------------------------------------ daily check
    def health_check(self, window_days=30, baseline_days=90, predictor=None) -> dict:
        cs, ce = self.window(window_days)
        bs, be = self.window(baseline_days, offset_days=window_days)
        cur = self.kpis(start=cs, end=ce)
        base = self.kpis(start=bs, end=be)
        alerts = []

        def alert(sev, title, detail, metric=None):
            alerts.append({"severity": sev, "title": title, "detail": detail, "metric": metric})

        # 1. overall SLA vs target and vs baseline
        if cur["res_sla"] is not None:
            gap = cur["gap_pts"]
            sev = "critical" if cur["status"] == "Below target" else "warning" if cur["status"] == "Watch" else "ok"
            alert(sev, f"Resolution SLA {pct(cur['res_sla'])} vs target {pct(cur['target'])} (last {window_days} days)",
                  f"Gap {gap:+.1f} pts. Previous {baseline_days} days: {pct(base['res_sla'])} "
                  f"({(cur['res_sla'] - base['res_sla']) * 100:+.1f} pts).", "res_sla")
        # 2. teams below target in the window
        d = self.frame(start=cs, end=ce)
        for t in self.data.group_kpis(d, "Team"):
            if t["status"] == "Below target":
                alert("critical" if t["gap_pts"] <= -8 else "warning",
                      f"{t['key']} below target: {pct(t['res_sla'])} vs {pct(t['target'])}",
                      f"Gap {t['gap_pts']:+.1f} pts on {t['total']:,} tickets, {t['breaches']} breaches.", "team")
        # 3. live queue
        q = self.frame()
        o = q[q.IsOpen == 1]
        due4 = o[(o.HoursToBreach > 0) & (o.HoursToBreach <= 4)]
        overdue = int((o.SLAStatus == "Open - Overdue").sum())
        if overdue:
            worst = o[o.SLAStatus == "Open - Overdue"].Team.value_counts()
            alert("critical" if overdue >= 20 else "warning", f"{overdue} open tickets already breached",
                  "Most in " + ", ".join(f"{k} ({v})" for k, v in worst.head(3).items()) + ".", "overdue")
        if len(due4):
            alert("warning", f"{len(due4)} tickets will breach in the next 4 hours",
                  ", ".join(due4.sort_values("HoursToBreach").TicketID.head(5)) + ".", "due_soon")
        # 4. structural patterns (whole history, so they are stable)
        for a in self.agent_outliers():
            alert("warning", f"{a['agent']} ({a['team']}) resolves {pct(a['res_sla'])} in SLA",
                  f"Team peers: {pct(a['peer_res_sla'])} ({a['gap_pts']:+.1f} pts); MTTR {a['mttr_hrs']} h vs {a['peer_mttr_hrs']} h.",
                  "agent")
        for a in self.reopen_outliers():
            alert("warning", f"{a['agent']} ({a['team']}) reopen rate {pct(a['reopen_rate'])}",
                  f"{'New joiner, ' if a['new_joiner'] else ''}{a['tenure_months']} months tenure; "
                  f"overall reopen rate {pct(a['overall_reopen_rate'])}. Suggest coaching / QA review.", "reopen")
        for t in self.time_outliers():
            alert("warning", f"{t['pattern']} miss response SLA {pct(t['response_breach_rate'])} of the time",
                  (t.get("hint") or "") + ".", "time")
        re = self.reassignment_effect()
        b = {x["handoffs"]: x["breach_rate"] for x in re["bands"]}
        if b.get("0") and b.get("3+") and b["3+"] > 3 * b["0"]:
            alert("warning", f"Reassignments drive breaches: {pct(b['0'])} with 0 hand-offs vs {pct(b['3+'])} with 3+",
                  f"Most reassigned team: {re['most_reassigned_team']['team']} "
                  f"({pct(re['most_reassigned_team']['multi_hop_share'])} of tickets hop 2+ times).", "reassign")
        for v in self.volume_anomalies():
            alert("info", f"{v['month']}: volume spike {v['tickets']:,} vs {v['typical_tickets']:,} typical",
                  f"SLA fell to {pct(v['res_sla'])} ({-v['sla_drop_pts']:+.1f} pts); driven by {v['surging_subcategory']} "
                  f"({pct(v['surging_share'])} of that month's tickets).", "volume")

        risk = predictor.top_risk(limit=8) if predictor is not None else None
        order = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
        alerts.sort(key=lambda a: order[a["severity"]])
        return {
            "as_of": self.as_of.strftime("%Y-%m-%d %H:%M"),
            "window": {"start": cs, "end": ce, "days": window_days},
            "baseline": {"start": bs, "end": be, "days": baseline_days},
            "current": cur, "previous": base,
            "status": cur["status"],
            "alerts": alerts,
            "counts": {s: sum(a["severity"] == s for a in alerts) for s in ("critical", "warning", "info")},
            "root_cause": self.root_cause(start=cs, end=ce),
            "root_cause_all_time": self.root_cause(),
            "at_risk_tickets": risk,
        }
