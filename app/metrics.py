"""
SLA metrics engine (pandas).

Every number on the dashboard comes from here, and the same functions will be
the agent's "tools" in Phase 2 - so the dashboard and the agent always agree.
Definitions mirror powerbi/DAX_Measures.dax.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
AGE_BUCKETS = ["0-4 h", "4-24 h", "1-3 d", "3-7 d", "7+ d"]
OPEN_STATUSES = ["Open - Overdue", "Open - At Risk", "Open - On Track"]
BREAKDOWN_DIMS = {
    "Team": "Team", "Priority": "PriorityShort", "Category": "Category",
    "SubCategory": "SubCategory", "Reassignments": "ReassignBand", "Shift": "Shift",
    "Channel": "Channel", "Weekday": "DayName", "Agent": "AgentName",
}


def _f(x, nd=4):
    """float -> rounded float, NaN -> None (JSON-safe)."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except TypeError:
        pass
    return round(float(x), nd)


def month_label(p: pd.Period) -> str:
    return p.strftime("%b") + (f" '{p.strftime('%y')}" if p.month == 1 else "")


class SLAData:
    def __init__(self, folder: Path = DATA_DIR):
        folder = Path(folder)
        dt_cols = ["CreatedDateTime", "FirstResponseDateTime", "ResolvedDateTime",
                   "ResponseDueDateTime", "ResolutionDueDateTime"]
        f = pd.read_csv(folder / "FactTickets.csv", parse_dates=dt_cols)
        pr = pd.read_csv(folder / "DimPriority.csv")
        tm = pd.read_csv(folder / "DimTeam.csv")
        ag = pd.read_csv(folder / "DimAgent.csv", parse_dates=["HireDate"])
        ct = pd.read_csv(folder / "DimCategory.csv")
        self.as_of = pd.read_csv(folder / "DimSnapshot.csv", parse_dates=["AsOfDateTime"])["AsOfDateTime"].iloc[0]

        f = (f.merge(pr[["PriorityKey", "Priority", "PriorityShort", "ComplianceTarget",
                         "ResolutionTargetHrs", "ResponseTargetMins"]], on="PriorityKey")
              .merge(tm[["TeamKey", "Team"]], on="TeamKey")
              .merge(ag[["AgentKey", "AgentName", "HireDate"]], on="AgentKey")
              .merge(ct[["CategoryKey", "Category", "SubCategory"]], on="CategoryKey"))
        f["CreatedDate"] = f["CreatedDateTime"].dt.normalize()
        f["Month"] = f["CreatedDateTime"].dt.to_period("M")
        f["ReassignBand"] = np.where(f.ReassignmentCount >= 3, "3+", f.ReassignmentCount.astype(str))
        f["Shift"] = np.where((f.CreatedHour >= 8) & (f.CreatedHour < 20), "Day", "Night")
        f["DayNo"] = f["CreatedDateTime"].dt.dayofweek
        f["DayName"] = f["DayNo"].map(dict(enumerate(DAY_NAMES)))
        age = (self.as_of - f["CreatedDateTime"]).dt.total_seconds() / 3600
        f["AgeHrs"] = np.where(f.IsOpen == 1, age, np.nan)
        f["HoursToBreach"] = np.where(
            f.IsOpen == 1, (f["ResolutionDueDateTime"] - self.as_of).dt.total_seconds() / 3600, np.nan)
        f["AgeBucket"] = pd.cut(f["AgeHrs"], [-1, 4, 24, 72, 168, 1e9], labels=AGE_BUCKETS)
        self.df = f
        self.teams = tm["Team"].tolist()
        self.priorities = pr.sort_values("SortOrder")["PriorityShort"].tolist()
        self.channels = sorted(f["Channel"].unique().tolist())
        self.min_date = f["CreatedDate"].min()
        self.max_date = f["CreatedDate"].max()

    # ------------------------------------------------------------------ filters
    def filter(self, start=None, end=None, priority=None, team=None, channel=None,
               apply_dates=True) -> pd.DataFrame:
        d = self.df
        if apply_dates and start:
            d = d[d.CreatedDate >= pd.Timestamp(start)]
        if apply_dates and end:
            d = d[d.CreatedDate <= pd.Timestamp(end)]
        if priority:
            d = d[d.PriorityShort == priority]
        if team:
            d = d[d.Team == team]
        if channel:
            d = d[d.Channel == channel]
        return d

    # ------------------------------------------------------------------ core KPIs
    @staticmethod
    def kpis(d: pd.DataFrame) -> dict:
        measured = d[d.ResolutionSLAMet.notna()]
        res = measured.ResolutionSLAMet.mean() if len(measured) else np.nan
        tgt = measured.ComplianceTarget.mean() if len(measured) else np.nan
        resolved = d[d.IsOpen == 0]
        csat = d.CSATScore.dropna()
        return {
            "total": int(len(d)),
            "open": int(d.IsOpen.sum()),
            "overdue": int((d.SLAStatus == "Open - Overdue").sum()),
            "at_risk": int((d.SLAStatus == "Open - At Risk").sum()),
            "res_sla": _f(res), "target": _f(tgt),
            "gap_pts": _f((res - tgt) * 100, 2) if len(measured) else None,
            "status": sla_status(res, tgt),
            "resp_sla": _f(d.ResponseSLAMet.mean()),
            "breaches": int((d.ResolutionSLAMet == 0).sum()),
            "resp_breaches": int((d.ResponseSLAMet == 0).sum()),
            "breach_rate": _f((measured.ResolutionSLAMet == 0).mean()) if len(measured) else None,
            "mtta_min": _f(d.ResponseMinutes.mean(), 1),
            "mttr_hrs": _f(d.ResolutionHours.mean(), 2),
            "p90_hrs": _f(d.ResolutionHours.quantile(0.9), 1),
            "avg_open_age_hrs": _f(d.AgeHrs.mean(), 1),
            "csat": _f(csat.mean(), 2),
            "csat_satisfied": _f((csat >= 4).mean()) if len(csat) else None,
            "reopen_rate": _f(resolved.Reopened.mean()) if len(resolved) else None,
            "multi_hop": _f((d.ReassignmentCount >= 2).mean()) if len(d) else None,
            "avg_reassign": _f(d.ReassignmentCount.mean(), 2),
        }

    def group_kpis(self, d: pd.DataFrame, col: str, keys=None) -> list[dict]:
        out = []
        for k, g in d.groupby(col, observed=True):
            out.append({"key": str(k), **self.kpis(g)})
        if keys is not None:
            order = {k: i for i, k in enumerate(keys)}
            out.sort(key=lambda r: order.get(r["key"], 999))
        return out

    # ------------------------------------------------------------------ pages
    def overview(self, **flt) -> dict:
        d = self.filter(**flt)
        nodate = self.filter(**{**flt, "start": None, "end": None})
        monthly = []
        res_by_month = nodate.dropna(subset=["ResolvedDateTime"]).ResolvedDateTime.dt.to_period("M")
        if flt.get("start"):
            res_by_month = res_by_month[nodate.loc[res_by_month.index, "ResolvedDateTime"] >= pd.Timestamp(flt["start"])]
        if flt.get("end"):
            res_by_month = res_by_month[nodate.loc[res_by_month.index, "ResolvedDateTime"] < pd.Timestamp(flt["end"]) + pd.Timedelta(days=1)]
        res_counts = res_by_month.value_counts()
        for m, g in d.groupby("Month"):
            k = self.kpis(g)
            monthly.append({"month": str(m), "label": month_label(m), "res_sla": k["res_sla"],
                            "target": k["target"], "created": k["total"],
                            "resolved": int(res_counts.get(m, 0))})
        if monthly:
            monthly[0]["label"] = month_label(pd.Period(monthly[0]["month"])).split(" ")[0] + \
                f" '{monthly[0]['month'][2:4]}"
            last = pd.Period(monthly[-1]["month"])
            monthly[-1]["mtd"] = bool(last == self.as_of.to_period("M"))
        prio = [{"priority": r["key"], "res_sla": r["res_sla"], "target": r["target"],
                 "status": r["status"], "total": r["total"]}
                for r in self.group_kpis(d, "PriorityShort", self.priorities)]
        teams = sorted(self.group_kpis(d, "Team"), key=lambda r: (r["gap_pts"] is None, r["gap_pts"]))
        return {"kpis": self.kpis(d), "monthly": monthly, "priority": prio, "teams": teams}

    def queue(self, limit=60, **flt) -> dict:
        d = self.filter(**flt)
        o = d[d.IsOpen == 1]
        by_team = []
        for t in self.teams:
            g = o[o.Team == t]
            if len(g):
                by_team.append({"team": t, **{s: int((g.SLAStatus == s).sum()) for s in OPEN_STATUSES},
                                "total": int(len(g))})
        by_team.sort(key=lambda r: -r["total"])
        aging = [{"bucket": b, "count": int((o.AgeBucket == b).sum())} for b in AGE_BUCKETS]
        cols = ["TicketID", "PriorityShort", "Team", "AgentName", "SubCategory", "Status",
                "SLAStatus", "CreatedDateTime", "ResolutionDueDateTime", "HoursToBreach"]
        rows = o.sort_values("HoursToBreach")[cols].head(limit)
        tickets = [{"id": r.TicketID, "priority": r.PriorityShort, "team": r.Team, "agent": r.AgentName,
                    "sub": r.SubCategory, "status": r.Status, "sla": r.SLAStatus,
                    "created": r.CreatedDateTime.strftime("%d %b %H:%M"),
                    "due": r.ResolutionDueDateTime.strftime("%d %b %H:%M"),
                    "hours_to_breach": _f(r.HoursToBreach, 1)} for r in rows.itertuples()]
        return {"kpis": self.kpis(d), "by_team": by_team, "aging": aging, "tickets": tickets}

    def people(self, agent=None, **flt) -> dict:
        d = self.filter(**flt)
        teams = []
        for t in sorted(self.group_kpis(d, "Team"), key=lambda r: (r["gap_pts"] is None, r["gap_pts"])):
            agents = self.group_kpis(d[d.Team == t["key"]], "AgentName")
            agents.sort(key=lambda r: (r["gap_pts"] is None, r["gap_pts"]))
            teams.append({**t, "agents": agents})
        scatter = [{"agent": r["key"], "team": d[d.AgentName == r["key"]].Team.iloc[0],
                    "total": r["total"], "res_sla": r["res_sla"], "target": r["target"]}
                   for r in self.group_kpis(d, "AgentName")]
        trend_src = d[d.AgentName == agent] if agent else d
        trend = []
        for m, g in trend_src.groupby("Month"):
            rs = g[g.IsOpen == 0]
            trend.append({"label": month_label(m), "reopen_rate": _f(rs.Reopened.mean()),
                          "res_sla": _f(g.ResolutionSLAMet.mean())})
        if trend:
            trend[0]["label"] = trend[0]["label"].split(" ")[0] + f" '{str(trend_src.Month.min())[2:4]}"
        return {"kpis": self.kpis(d), "teams": teams, "scatter": scatter, "trend": trend,
                "agent": agent}

    def breakdown(self, path=None, dim="Team", **flt) -> dict:
        """Decomposition: filter by path [(dim, value), ...] then split by `dim`."""
        d = self.filter(**flt)
        for pdim, val in (path or []):
            d = d[d[BREAKDOWN_DIMS[pdim]].astype(str) == str(val)]
        col = BREAKDOWN_DIMS[dim]
        rows = []
        for k, g in d.groupby(col, observed=True):
            m = g[g.ResolutionSLAMet.notna()]
            b = int((m.ResolutionSLAMet == 0).sum())
            rows.append({"value": str(k), "breaches": b, "measured": int(len(m)),
                         "breach_rate": _f(b / len(m)) if len(m) else None})
        rows.sort(key=lambda r: -r["breaches"])
        total_b = int((d.ResolutionSLAMet == 0).sum())
        return {"dim": dim, "path": path or [], "rows": rows, "breaches": total_b,
                "measured": int(d.ResolutionSLAMet.notna().sum())}

    def rootcause(self, **flt) -> dict:
        d = self.filter(**flt)
        bands = []
        for b in ["0", "1", "2", "3+"]:
            m = d[(d.ReassignBand == b) & d.ResolutionSLAMet.notna()]
            bands.append({"band": b, "breach_rate": _f((m.ResolutionSLAMet == 0).mean()) if len(m) else None,
                          "tickets": int(len(m))})
        r = d[d.ResponseSLAMet.notna()]
        piv = (r.assign(b=(r.ResponseSLAMet == 0).astype(float))
                .pivot_table(index="DayNo", columns="CreatedHour", values="b", aggfunc="mean"))
        cnt = r.pivot_table(index="DayNo", columns="CreatedHour", values="TicketID", aggfunc="count")
        heat = [[_f(piv.at[dn, h]) if (dn in piv.index and h in piv.columns) else None
                 for h in range(24)] for dn in range(7)]
        heat_n = [[int(cnt.at[dn, h]) if (dn in cnt.index and h in cnt.columns and not pd.isna(cnt.at[dn, h])) else 0
                   for h in range(24)] for dn in range(7)]
        # rolling 30-day resolution SLA by created date
        daily = d.groupby("CreatedDate").agg(met=("ResolutionSLAMet", "sum"), n=("ResolutionSLAMet", "count"))
        if len(daily):
            idx = pd.date_range(daily.index.min(), daily.index.max())
            daily = daily.reindex(idx, fill_value=0)
            roll = daily.rolling(30, min_periods=7).sum()
            rolling = [{"date": i.strftime("%Y-%m-%d"), "v": _f(r.met / r.n) if r.n else None}
                       for i, r in roll.iterrows()]
        else:
            rolling = []
        return {"kpis": self.kpis(d), "bands": bands, "heat": heat, "heat_n": heat_n,
                "days": DAY_NAMES, "rolling": rolling,
                "tree": self.breakdown(dim="Team", **flt)}

    def ticket(self, ticket_id: str) -> dict | None:
        t = self.df[self.df.TicketID == ticket_id]
        if t.empty:
            return None
        r = t.iloc[0]
        ts = lambda x: None if pd.isna(x) else x.strftime("%d %b %Y, %H:%M")
        return {
            "id": r.TicketID, "priority": r.Priority, "team": r.Team, "agent": r.AgentName,
            "category": r.Category, "sub": r.SubCategory, "channel": r.Channel, "status": r.Status,
            "sla": r.SLAStatus, "reassign": int(r.ReassignmentCount), "reopened": bool(r.Reopened),
            "csat": None if pd.isna(r.CSATScore) else int(r.CSATScore),
            "response_mins": _f(r.ResponseMinutes, 1), "resolution_hrs": _f(r.ResolutionHours, 2),
            "response_target_mins": int(r.ResponseTargetMins), "resolution_target_hrs": int(r.ResolutionTargetHrs),
            "timeline": [
                {"step": "Created", "at": ts(r.CreatedDateTime)},
                {"step": "Response due", "at": ts(r.ResponseDueDateTime)},
                {"step": "First response", "at": ts(r.FirstResponseDateTime),
                 "ok": None if pd.isna(r.ResponseSLAMet) else bool(r.ResponseSLAMet)},
                {"step": "Resolution due", "at": ts(r.ResolutionDueDateTime)},
                {"step": "Resolved", "at": ts(r.ResolvedDateTime),
                 "ok": None if pd.isna(r.ResolutionSLAMet) else bool(r.ResolutionSLAMet)},
            ],
            "hours_to_breach": _f(r.HoursToBreach, 1),
        }


def sla_status(value, target):
    if value is None or target is None or pd.isna(value) or pd.isna(target):
        return None
    if value >= target:
        return "On target"
    if value >= target - 0.03:
        return "Watch"
    return "Below target"


if __name__ == "__main__":      # quick self-check
    s = SLAData()
    k = s.kpis(s.df)
    print({x: k[x] for x in ["total", "res_sla", "target", "breaches", "resp_breaches", "open", "overdue", "at_risk"]})
