"""
Breach-risk model for open tickets (scikit-learn, trains in a few seconds).

Target   : resolution SLA breached (ResolutionSLAMet == 0) on tickets whose outcome is known
Features : what is known about a ticket while it is still open - priority, team,
           sub-category, channel, agent, hour / weekday created, agent tenure,
           current reassignment count
Model    : HistGradientBoostingClassifier with native categorical support (categories as integer codes)
Validation: time-based split (train on older tickets, test on the most recent 60 days)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from metrics import SLAData, _f

CAT = ["PriorityShort", "Team", "SubCategory", "Channel", "AgentName"]
NUM = ["CreatedHour", "DayNo", "ReassignmentCount", "TenureDays", "Night", "Weekend"]


class BreachPredictor:
    def __init__(self, data: SLAData, test_days: int = 60, seed: int = 42):
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.metrics import average_precision_score, roc_auc_score

        self.data = data
        df = data.df
        X = self._features(df)
        known = df.ResolutionSLAMet.notna()
        y = (df.ResolutionSLAMet == 0).astype(int)

        cutoff = data.as_of.normalize() - pd.Timedelta(days=test_days)
        tr = known & (df.CreatedDateTime < cutoff)
        te = known & (df.CreatedDateTime >= cutoff)

        def model():
            return HistGradientBoostingClassifier(
                categorical_features=[X.columns.get_loc(c) for c in CAT],
                max_iter=250, learning_rate=0.08, max_leaf_nodes=31,
                l2_regularization=1.0, random_state=seed)

        m = model().fit(X[tr], y[tr])
        p = m.predict_proba(X[te])[:, 1]
        self.metrics = {
            "roc_auc": _f(roc_auc_score(y[te], p), 3),
            "pr_auc": _f(average_precision_score(y[te], p), 3),
            "base_rate": _f(y[te].mean(), 3),
            "train_rows": int(tr.sum()), "test_rows": int(te.sum()),
            "test_period": f"{cutoff:%Y-%m-%d} to {data.as_of:%Y-%m-%d}",
        }
        # final model on everything we know
        self.model = model().fit(X[known], y[known])
        self._X = X
        # group breach rates used to explain individual predictions
        m_all = df[known]
        self._rates = {c: (m_all.ResolutionSLAMet == 0).groupby(m_all[c]).mean() for c in CAT}
        self._rates["ReassignBand"] = (m_all.ResolutionSLAMet == 0).groupby(m_all.ReassignBand).mean()
        self._base = float((m_all.ResolutionSLAMet == 0).mean())

    @staticmethod
    def _features(df: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(index=df.index)
        for c in CAT:                       # integer codes work on every scikit-learn version
            X[c] = df[c].astype("category").cat.codes.astype("float").replace(-1, float("nan"))
        X["CreatedHour"] = df.CreatedHour
        X["DayNo"] = df.DayNo
        X["ReassignmentCount"] = df.ReassignmentCount
        X["TenureDays"] = (df.CreatedDateTime - df.HireDate).dt.days.clip(lower=0)
        X["Night"] = ((df.CreatedHour < 8) | (df.CreatedHour >= 20)).astype(int)
        X["Weekend"] = (df.DayNo >= 5).astype(int)
        return X

    def _reasons(self, r) -> list[str]:
        out = []
        for col, label in [("ReassignBand", "reassigned {v} times"), ("AgentName", "agent {v}"),
                           ("Team", "{v}"), ("PriorityShort", "{v}"), ("SubCategory", "{v}")]:
            v = getattr(r, col)
            rate = self._rates[col].get(v)
            if rate is not None and rate >= 1.6 * self._base:
                out.append(f"{label.format(v=v)} ({rate * 100:.0f}% breach history)")
        return out[:3]

    def score_open(self) -> pd.DataFrame:
        df = self.data.df
        o = df[(df.IsOpen == 1)].copy()
        if o.empty:
            return o
        o["risk"] = self.model.predict_proba(self._X.loc[o.index])[:, 1]
        # already overdue = certain breach
        o.loc[o.HoursToBreach <= 0, "risk"] = 1.0
        return o

    def top_risk(self, limit=10, team=None, priority=None, include_overdue=False) -> dict:
        o = self.score_open()
        if team:
            o = o[o.Team == team]
        if priority:
            o = o[o.PriorityShort == priority]
        if not include_overdue:
            o = o[o.HoursToBreach > 0]
        o = o.sort_values(["risk", "HoursToBreach"], ascending=[False, True]).head(limit)
        rows = [{"ticket": r.TicketID, "priority": r.PriorityShort, "team": r.Team, "agent": r.AgentName,
                 "subcategory": r.SubCategory, "reassignments": int(r.ReassignmentCount),
                 "hours_to_breach": _f(r.HoursToBreach, 1), "breach_risk": _f(r.risk, 3),
                 "why": self._reasons(r)} for r in o.itertuples()]
        return {"model": self.metrics, "tickets": rows}
