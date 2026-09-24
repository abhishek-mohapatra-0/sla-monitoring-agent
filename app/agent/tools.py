"""
Tools the agent can call. Each tool = a JSON schema (sent to the LLM) + a Python function.

The LLM decides WHICH tool to call and with WHAT arguments; the numbers always
come from pandas (metrics.py / analysis.py / predictor.py).
"""
from __future__ import annotations

import json
from typing import Any, Callable

from metrics import BREAKDOWN_DIMS

FILTER_PROPS = {
    "start": {"type": "string", "description": "Created-date from, YYYY-MM-DD (inclusive)"},
    "end": {"type": "string", "description": "Created-date to, YYYY-MM-DD (inclusive)"},
    "team": {"type": "string", "description": "Exact team name"},
    "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
    "channel": {"type": "string", "description": "Exact channel name"},
}
FILTER_KEYS = ("start", "end", "team", "priority", "channel")


def _schema(name, description, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


class Toolbox:
    def __init__(self, data, analyst, predictor_factory: Callable[[], Any]):
        self.data = data
        self.an = analyst
        self._pred_factory = predictor_factory
        self.specs = [
            _schema("get_kpis",
                    "SLA KPIs (resolution/response SLA %, target, gap, breaches, open/overdue, MTTR, "
                    "MTTA, CSAT, reopen rate) for any filter combination. Use for 'what is / how many' questions.",
                    {**FILTER_PROPS, "agent": {"type": "string", "description": "Exact agent name"}}),
            _schema("compare_periods",
                    "Compare KPIs of two date ranges (e.g. this month vs last month, March vs February).",
                    {"a_start": {"type": "string"}, "a_end": {"type": "string"},
                     "b_start": {"type": "string"}, "b_end": {"type": "string"},
                     "team": FILTER_PROPS["team"], "priority": FILTER_PROPS["priority"]},
                    ["a_start", "a_end", "b_start", "b_end"]),
            _schema("monthly_trend", "Month-by-month tickets, resolution SLA %, target, breaches, MTTR.",
                    {"team": FILTER_PROPS["team"], "priority": FILTER_PROPS["priority"],
                     "channel": FILTER_PROPS["channel"]}),
            _schema("breakdown",
                    "Breaches and breach rate split by one dimension, optionally inside a drill path "
                    "(like one level of a decomposition tree).",
                    {**FILTER_PROPS,
                     "dimension": {"type": "string", "enum": list(BREAKDOWN_DIMS)},
                     "path": {"type": "array", "description": "Drill path, e.g. [{\"dimension\":\"Team\",\"value\":\"Network Ops\"}]",
                              "items": {"type": "object", "properties": {
                                  "dimension": {"type": "string", "enum": list(BREAKDOWN_DIMS)},
                                  "value": {"type": "string"}}}}},
                    ["dimension"]),
            _schema("root_cause",
                    "WHY are we breaching? Automatic drill-down that finds the segment explaining the most "
                    "excess breaches (team, priority, sub-category, reassignments, shift, agent...) plus the "
                    "top drivers. Use for any 'why' question; filter by dates for a specific period.",
                    FILTER_PROPS),
            _schema("find_outliers",
                    "Known problem patterns: slow agents vs team peers, agents with high reopen rates, "
                    "night/weekend response problems, reassignment effect, monthly volume spikes.",
                    {"kind": {"type": "string", "enum": ["all", "agents", "reopen", "time", "reassignment", "volume"]},
                     "team": FILTER_PROPS["team"]}),
            _schema("predict_breach_risk",
                    "Machine-learning breach risk for OPEN tickets that have not breached yet, highest risk "
                    "first, with reasons and the model's accuracy (ROC AUC).",
                    {"limit": {"type": "integer", "description": "How many tickets (default 10)"},
                     "team": FILTER_PROPS["team"], "priority": FILTER_PROPS["priority"]}),
            _schema("open_queue",
                    "Open tickets right now sorted by hours to breach (negative = already overdue). within_hours returns only tickets not yet breached that are due within N hours; status='Open - Overdue' returns breached ones.",
                    {"within_hours": {"type": "number", "description": "Only tickets due within this many hours"},
                     "team": FILTER_PROPS["team"], "priority": FILTER_PROPS["priority"],
                     "status": {"type": "string", "enum": ["Open - Overdue", "Open - At Risk", "Open - On Track"]},
                     "limit": {"type": "integer"}}),
            _schema("get_ticket", "Full details and timeline of one ticket.",
                    {"ticket_id": {"type": "string", "description": "e.g. INC1059600"}}, ["ticket_id"]),
            _schema("health_check",
                    "Today's full SLA briefing: status, alerts by severity, root cause of the last 30 days, "
                    "tickets at risk. Use for 'summary', 'status', 'how are we doing', 'daily report'."),
            _schema("list_values", "Valid values for a dimension (teams, agents, sub-categories, channels...).",
                    {"dimension": {"type": "string", "enum": list(BREAKDOWN_DIMS) + ["Category"]}}, ["dimension"]),
        ]
        self.funcs = {s["function"]["name"]: getattr(self, s["function"]["name"]) for s in self.specs}

    @property
    def predictor(self):
        return self._pred_factory()

    # ----------------------------------------------------------- dispatcher
    def call(self, name: str, args: dict | str | None) -> dict:
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                return {"error": f"Arguments for {name} were not valid JSON"}
        args = {k: v for k, v in (args or {}).items() if v not in (None, "", [])}
        fn = self.funcs.get(name)
        if fn is None:
            return {"error": f"Unknown tool {name}"}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:          # keep the conversation alive
            return {"error": f"{type(e).__name__}: {e}"}

    # ----------------------------------------------------------- validation helpers
    def _norm(self, **flt):
        out = {}
        for k in FILTER_KEYS + ("agent",):
            v = flt.get(k)
            if not v:
                continue
            if k == "team":
                v = self._match(v, self.data.teams, "team")
            elif k == "channel":
                v = self._match(v, self.data.channels, "channel")
            elif k == "priority":
                v = str(v).upper()[:2]
            elif k == "agent":
                v = self._match(v, sorted(self.data.df.AgentName.unique()), "agent")
            out[k] = v
        return out

    @staticmethod
    def _match(v, options, what):
        for o in options:
            if o.lower() == str(v).lower():
                return o
        for o in options:
            if str(v).lower() in o.lower():
                return o
        raise ValueError(f"Unknown {what} '{v}'. Valid: {', '.join(options)}")

    # ----------------------------------------------------------- tools
    def get_kpis(self, **flt):
        return self.an.kpis(**self._norm(**flt))

    def compare_periods(self, a_start, a_end, b_start, b_end, team=None, priority=None):
        common = self._norm(team=team, priority=priority)
        return self.an.compare({"start": a_start, "end": a_end}, {"start": b_start, "end": b_end},
                               label_a=f"{a_start}..{a_end}", label_b=f"{b_start}..{b_end}", **common)

    def monthly_trend(self, **flt):
        return {"months": self.an.monthly_trend(**self._norm(**flt))}

    def breakdown(self, dimension, path=None, **flt):
        p = [(x["dimension"], x["value"]) for x in (path or []) if "dimension" in x and "value" in x]
        r = self.data.breakdown(path=p, dim=dimension, **self._norm(**flt))
        r["rows"] = r["rows"][:15]
        return r

    def root_cause(self, **flt):
        return self.an.root_cause(**self._norm(**flt))

    def find_outliers(self, kind="all", team=None):
        return self.an.outliers(kind=kind, **self._norm(team=team))

    def predict_breach_risk(self, limit=10, team=None, priority=None):
        return self.predictor.top_risk(limit=min(int(limit), 30), **self._norm(team=team, priority=priority))

    def open_queue(self, within_hours=None, team=None, priority=None, status=None, limit=15):
        flt = self._norm(team=team, priority=priority)
        d = self.data.filter(**flt)
        o = d[d.IsOpen == 1]
        if status:
            o = o[o.SLAStatus == status]
        if within_hours is not None:          # due soon = not breached yet, due within N hours
            o = o[(o.HoursToBreach > 0) & (o.HoursToBreach <= float(within_hours))]
        o = o.sort_values("HoursToBreach")
        rows = [{"ticket": r.TicketID, "priority": r.PriorityShort, "team": r.Team, "agent": r.AgentName,
                 "subcategory": r.SubCategory, "status": r.SLAStatus,
                 "hours_to_breach": round(float(r.HoursToBreach), 1)} for r in o.head(int(limit)).itertuples()]
        return {"count": int(len(o)), "overdue": int((o.SLAStatus == "Open - Overdue").sum()), "tickets": rows}

    def get_ticket(self, ticket_id):
        t = self.data.ticket(str(ticket_id).strip().upper())
        return t or {"error": f"Ticket {ticket_id} not found"}

    def health_check(self):
        h = self.an.health_check(predictor=self.predictor)
        # keep the LLM payload compact
        h["root_cause"].pop("drivers", None)
        h["root_cause_all_time"].pop("drivers", None)
        h["at_risk_tickets"]["tickets"] = h["at_risk_tickets"]["tickets"][:5]
        return h

    def list_values(self, dimension):
        col = "Category" if dimension == "Category" else BREAKDOWN_DIMS[dimension]
        return {"dimension": dimension, "values": sorted(map(str, self.data.df[col].dropna().unique()))}
