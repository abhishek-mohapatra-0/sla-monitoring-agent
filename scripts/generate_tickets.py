"""
Synthetic IT Service Desk ticket generator for the SLA Monitoring Agent project.

Generates ~12 months of realistic tickets as a Power BI-ready star schema:
    FactTickets, DimPriority, DimTeam, DimAgent, DimCategory, DimDate, DimSnapshot

Built-in patterns (the agent will be asked to discover these later):
  1. Network Ops P2 tickets get reassigned a lot -> resolution breaches
  2. One Application Support agent is much slower than peers
  3. A new Service Desk joiner (hired Jun-2026) has a high reopen rate
  4. Overnight P3 tickets breach response SLA (no night shift for P3/P4)
  5. Weekends are understaffed -> slower response
  6. A 2-week "ERP migration" surge in March 2026 -> volume spike + SLA dip
  7. Mondays carry ~30% more volume

Usage:  python generate_tickets.py  [--seed 42] [--out ../data]
Only needs numpy + pandas (free).
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------- config
START = pd.Timestamp("2025-09-01 00:00")
AS_OF = pd.Timestamp("2026-09-22 18:00")          # "now" for the snapshot
SURGE_START, SURGE_END = pd.Timestamp("2026-03-09"), pd.Timestamp("2026-03-22")
BASE_DAILY = 190                                   # avg weekday tickets
SHIFT_START_HOUR, SHIFT_END_HOUR = 8, 20           # day shift for P3/P4

PRIORITIES = pd.DataFrame({
    "PriorityKey": [1, 2, 3, 4],
    "Priority": ["P1 - Critical", "P2 - High", "P3 - Medium", "P4 - Low"],
    "PriorityShort": ["P1", "P2", "P3", "P4"],
    "ResponseTargetMins": [15, 30, 120, 480],
    "ResolutionTargetHrs": [4, 8, 24, 72],
    "ComplianceTarget": [0.98, 0.95, 0.92, 0.90],
    "SortOrder": [1, 2, 3, 4],
})

TEAMS = pd.DataFrame({
    "TeamKey": [1, 2, 3, 4, 5, 6],
    "Team": ["Service Desk", "Network Ops", "Application Support",
             "Infrastructure", "Database", "Security Ops"],
    "SupportLevel": ["L1", "L2", "L2", "L3", "L3", "L3"],
    "Location": ["Bengaluru", "Bengaluru", "Pune", "Hyderabad", "Pune", "Bengaluru"],
})
TEAM_SIZE = {1: 14, 2: 6, 3: 9, 4: 5, 5: 3, 6: 3}
TEAM_SPEED = {1: 0.9, 2: 1.05, 3: 1.0, 4: 1.1, 5: 1.0, 6: 0.85}

# Category, SubCategory, TeamKey, weight, priority mix (P1..P4), complexity
CATEGORIES = [
    ("Access & Identity", "Password Reset",    1, 11, [0.00, 0.03, 0.37, 0.60], 0.5),
    ("Access & Identity", "Account Unlock",    1,  6, [0.00, 0.05, 0.45, 0.50], 0.5),
    ("Access & Identity", "Access Request",    1,  8, [0.00, 0.04, 0.36, 0.60], 0.9),
    ("Hardware",          "Laptop / Desktop",  1,  8, [0.01, 0.08, 0.51, 0.40], 1.2),
    ("Hardware",          "Printer",           1,  4, [0.00, 0.03, 0.37, 0.60], 0.9),
    ("Hardware",          "Peripherals",       1,  3, [0.00, 0.02, 0.28, 0.70], 0.8),
    ("Network",           "VPN",               2,  6, [0.03, 0.22, 0.55, 0.20], 1.0),
    ("Network",           "Wi-Fi",             2,  4, [0.02, 0.15, 0.58, 0.25], 1.0),
    ("Network",           "LAN / Connectivity", 2, 3, [0.06, 0.25, 0.49, 0.20], 1.1),
    ("Application",       "ERP (SAP)",         3,  7, [0.05, 0.20, 0.55, 0.20], 1.2),
    ("Application",       "CRM",               3,  4, [0.03, 0.15, 0.57, 0.25], 1.0),
    ("Application",       "Email / Outlook",   3,  7, [0.02, 0.10, 0.53, 0.35], 0.8),
    ("Application",       "MS Office",         3,  5, [0.00, 0.05, 0.45, 0.50], 0.7),
    ("Infrastructure",    "Server",            4,  3, [0.10, 0.25, 0.50, 0.15], 1.2),
    ("Infrastructure",    "Storage",           4,  2, [0.06, 0.20, 0.54, 0.20], 1.1),
    ("Infrastructure",    "Cloud VM",          4,  2, [0.05, 0.20, 0.55, 0.20], 1.0),
    ("Database",          "Performance",       5,  2, [0.08, 0.30, 0.47, 0.15], 1.2),
    ("Database",          "Backup / Restore",  5,  1, [0.06, 0.24, 0.50, 0.20], 1.0),
    ("Security",          "Phishing Report",   6,  3, [0.03, 0.27, 0.50, 0.20], 0.6),
    ("Security",          "Malware Alert",     6,  1, [0.20, 0.40, 0.35, 0.05], 1.0),
]

CHANNELS = ["Portal", "Email", "Phone", "Chat"]
CHANNEL_W = [0.45, 0.25, 0.20, 0.10]
CHANNEL_RESP = {"Portal": 1.0, "Email": 1.15, "Phone": 0.45, "Chat": 0.6}

FIRST = ["Aarav", "Diya", "Rohan", "Ananya", "Vikram", "Isha", "Karan", "Meera",
         "Arjun", "Sneha", "Rahul", "Pooja", "Nikhil", "Kavya", "Siddharth",
         "Riya", "Aditya", "Neha", "Manish", "Tanvi", "Varun", "Shreya", "Harsh",
         "Priya", "Amit", "Divya", "Kunal", "Nisha", "Gaurav", "Swati", "Yash",
         "Anjali", "Deepak", "Ritika", "Sameer", "Aditi", "Tarun", "Megha",
         "Vivek", "Sakshi"]
LAST = ["Sharma", "Iyer", "Reddy", "Nair", "Patel", "Das", "Rao", "Menon",
        "Gupta", "Joshi", "Kulkarni", "Singh", "Mishra", "Pillai", "Bose",
        "Hegde", "Verma", "Shetty", "Chopra", "Sahu"]


def build_agents(rng):
    rows, key = [], 1
    names = rng.permutation(FIRST)
    for team_key, size in TEAM_SIZE.items():
        for i in range(size):
            name = f"{names[key - 1]} {rng.choice(LAST)}"
            hire = pd.Timestamp("2019-01-01") + pd.Timedelta(days=int(rng.integers(0, 2200)))
            speed = float(np.exp(rng.normal(0, 0.12)))
            reopen = 0.04
            if team_key == 3 and i == 0:        # PATTERN 2: slow App Support agent
                speed = 1.9
            if team_key == 1 and i == 0:        # PATTERN 3: new joiner, high reopens
                hire, speed, reopen = pd.Timestamp("2026-06-02"), 1.35, 0.16
            if team_key == 1 and i == 1:        # a strong performer
                speed = 0.7
            level = TEAMS.loc[TEAMS.TeamKey == team_key, "SupportLevel"].iat[0]
            rows.append(dict(AgentKey=key, AgentName=name, TeamKey=team_key,
                             Level=level, HireDate=hire.date(),
                             _speed=speed, _reopen=reopen))
            key += 1
    return pd.DataFrame(rows)


def arrivals(rng):
    """Poisson arrivals per day with weekday, month and surge effects."""
    hour_w = np.array([1, 0.6, 0.5, 0.4, 0.4, 0.6, 1.2, 2.5, 5, 8, 9.5, 9, 7,
                       7.5, 8.5, 8, 7, 5.5, 4, 3, 2.3, 1.8, 1.5, 1.2])
    hour_w = hour_w / hour_w.sum()
    days = pd.date_range(START.normalize(), AS_OF.normalize(), freq="D")
    out = []
    for d in days:
        dow = d.dayofweek
        f = {0: 1.3, 1: 1.05, 2: 1.0, 3: 1.0, 4: 0.9, 5: 0.35, 6: 0.25}[dow]
        f *= 1 + 0.08 * np.sin(2 * np.pi * (d.month - 1) / 12)      # mild seasonality
        if d.month == 12 and d.day > 22:
            f *= 0.5                                                 # holidays
        if SURGE_START <= d <= SURGE_END:
            f *= 1.55                                                # PATTERN 6
        n = rng.poisson(BASE_DAILY * f)
        hrs = rng.choice(24, size=n, p=hour_w)
        mins = rng.integers(0, 60, size=n)
        secs = rng.integers(0, 60, size=n)
        ts = d + pd.to_timedelta(hrs, "h") + pd.to_timedelta(mins, "m") + pd.to_timedelta(secs, "s")
        out.append(ts[ts <= AS_OF])
    return pd.DatetimeIndex(np.concatenate(out)).sort_values()


def next_shift_start(ts):
    """For off-hours tickets, time when the day shift picks them up."""
    h = ts.hour
    if SHIFT_START_HOUR <= h < SHIFT_END_HOUR:
        return ts
    base = ts.normalize() + pd.Timedelta(hours=SHIFT_START_HOUR, minutes=30)
    return base if h < SHIFT_START_HOUR else base + pd.Timedelta(days=1)


def main(seed, out_dir):
    rng = np.random.default_rng(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    agents = build_agents(rng)
    cats = pd.DataFrame(CATEGORIES, columns=["Category", "SubCategory", "TeamKey",
                                             "_w", "_pmix", "_cx"])
    cats.insert(0, "CategoryKey", range(1, len(cats) + 1))

    created = arrivals(rng)
    n = len(created)
    in_surge = (created >= SURGE_START) & (created < SURGE_END + pd.Timedelta(days=1))

    # --- category (surge pushes ERP tickets up)
    w = cats["_w"].to_numpy(float)
    cat_idx = rng.choice(len(cats), size=n, p=w / w.sum())
    erp = cats.index[cats.SubCategory == "ERP (SAP)"][0]
    surge_mask = in_surge & (rng.random(n) < 0.35)
    cat_idx[surge_mask] = erp
    c = cats.iloc[cat_idx].reset_index(drop=True)

    # --- priority
    pmix = np.vstack(c["_pmix"].to_numpy())
    u = rng.random(n)[:, None]
    prio = (u > np.cumsum(pmix, axis=1)).sum(axis=1) + 1
    prio = np.clip(prio, 1, 4)
    pr = PRIORITIES.set_index("PriorityKey").loc[prio].reset_index()

    # --- team / agent
    team = c["TeamKey"].to_numpy()
    agent_key = np.empty(n, dtype=int)
    for t in TEAMS.TeamKey:
        idx = np.where(team == t)[0]
        pool = agents[agents.TeamKey == t]
        # new joiner only gets tickets after hire date
        cand = pool.AgentKey.to_numpy()
        hires = pd.to_datetime(pool.HireDate).to_numpy()
        for i in idx:
            ok = cand[hires <= created[i].to_datetime64()]
            agent_key[i] = rng.choice(ok)
    ag = agents.set_index("AgentKey").loc[agent_key].reset_index()

    channel = rng.choice(CHANNELS, size=n, p=CHANNEL_W)
    dow = created.dayofweek.to_numpy()
    hour = created.hour.to_numpy()

    # --- first response
    resp_target = pr["ResponseTargetMins"].to_numpy(float)
    resp = resp_target * 0.32 * np.exp(rng.normal(0, 0.55, n))
    resp *= ag["_speed"].to_numpy() ** 0.5
    resp *= np.array([CHANNEL_RESP[ch] for ch in channel])
    resp *= np.where(dow >= 5, 1.9, 1.0)                  # PATTERN 5 weekends
    resp *= np.where(dow == 0, 1.25, 1.0)                 # PATTERN 7 Monday load
    resp *= np.where(in_surge, 1.6, 1.0)
    # PATTERN 4: P3/P4 created off-hours wait for the day shift to pick them up
    off = (prio >= 3) & ((hour < SHIFT_START_HOUR) | (hour >= SHIFT_END_HOUR))
    for i in np.where(off)[0]:
        pick = next_shift_start(created[i])
        wait = (pick - created[i]).total_seconds() / 60
        resp[i] = wait + resp[i] * 0.5
    first_resp = created + pd.to_timedelta(resp, "m")

    # --- reassignments
    lam = np.full(n, 0.25)
    lam[(team == 2) & (prio == 2)] = 2.3                 # PATTERN 1
    lam[(team == 2) & (prio != 2)] = 0.6
    lam[c["SubCategory"].to_numpy() == "ERP (SAP)"] = 0.8
    lam[in_surge] += 0.5
    reassign = rng.poisson(lam)

    # --- resolution
    res_target = pr["ResolutionTargetHrs"].to_numpy(float)
    res = res_target * 0.33 * np.exp(rng.normal(0, 0.6, n))
    res *= ag["_speed"].to_numpy()
    res *= np.array([TEAM_SPEED[t] for t in team])
    res *= c["_cx"].to_numpy()
    res *= np.where(in_surge, 1.45, 1.0)
    res += reassign * res_target * rng.uniform(0.15, 0.4, n)
    # long tail: tickets stuck waiting on user / vendor / change window
    stuck = rng.random(n) < np.where(prio >= 3, 0.03, 0.01)
    res += np.where(stuck, res_target * rng.uniform(0.8, 6.0, n), 0)
    res = np.maximum(res, resp / 60 + 0.05)
    resolved = created + pd.to_timedelta(res, "h")

    # --- open vs closed at snapshot
    is_open = resolved > AS_OF
    has_resp = first_resp <= AS_OF
    status = np.where(~is_open,
                      np.where(resolved < AS_OF - pd.Timedelta(days=3), "Closed", "Resolved"),
                      np.where(~has_resp, "New",
                               np.where(rng.random(n) < 0.18, "On Hold", "In Progress")))

    resp_due = created + pd.to_timedelta(resp_target, "m")
    res_due = created + pd.to_timedelta(res_target, "h")

    resp_met = np.where(has_resp, (resp <= resp_target).astype(float),
                        np.where(AS_OF > resp_due, 0.0, np.nan))
    res_met = np.where(~is_open, (res <= res_target).astype(float),
                       np.where(AS_OF > res_due, 0.0, np.nan))

    # SLA status as of snapshot
    elapsed_pct = ((AS_OF - created).total_seconds() / 3600) / res_target
    sla_status = np.select(
        [~is_open & (res_met == 1), ~is_open & (res_met == 0),
         is_open & (AS_OF > res_due), is_open & (elapsed_pct >= 0.75)],
        ["Met", "Breached", "Open - Overdue", "Open - At Risk"],
        default="Open - On Track")

    # --- reopen + CSAT
    reopen_p = ag["_reopen"].to_numpy() + np.where(res < res_target * 0.1, 0.03, 0)
    reopened = ((rng.random(n) < reopen_p) & ~is_open).astype(int)
    csat_mean = (4.4 - 1.3 * (res_met == 0) - 0.9 * reopened - 0.25 * np.minimum(reassign, 4)
                 - 0.4 * (resp_met == 0))
    csat = np.clip(np.round(csat_mean + rng.normal(0, 0.7, n)), 1, 5)
    csat = np.where((rng.random(n) < 0.35) & ~is_open, csat, np.nan)

    fact = pd.DataFrame({
        "TicketID": [f"INC{1_000_000 + i}" for i in range(n)],
        "CreatedDateTime": created.floor("s"),
        "CreatedDate": created.normalize().date,
        "CreatedHour": hour,
        "PriorityKey": prio,
        "CategoryKey": c["CategoryKey"],
        "TeamKey": team,
        "AgentKey": agent_key,
        "Channel": channel,
        "Status": status,
        "IsOpen": is_open.astype(int),
        "FirstResponseDateTime": pd.Series(first_resp.floor("s")).where(has_resp),
        "ResolvedDateTime": pd.Series(resolved.floor("s")).where(~is_open),
        "ResolvedDate": pd.Series(resolved.normalize().date).where(~is_open),
        "ResponseDueDateTime": resp_due.floor("s"),
        "ResolutionDueDateTime": res_due.floor("s"),
        "ResponseMinutes": np.where(has_resp, np.round(resp, 1), np.nan),
        "ResolutionHours": np.where(~is_open, np.round(res, 2), np.nan),
        "ResponseSLAMet": resp_met,
        "ResolutionSLAMet": res_met,
        "SLAStatus": sla_status,
        "ReassignmentCount": reassign,
        "Reopened": reopened,
        "CSATScore": csat,
    })
    fact["ResolvedDate"] = pd.to_datetime(fact["ResolvedDate"]).dt.date
    for col in ["ResponseSLAMet", "ResolutionSLAMet", "CSATScore"]:
        fact[col] = fact[col].astype("Int64")         # 1/0/blank, no decimals

    # --- DimDate
    dates = pd.date_range(START.normalize(), AS_OF.normalize() + pd.Timedelta(days=10))
    dim_date = pd.DataFrame({
        "Date": dates.date,
        "Year": dates.year,
        "Quarter": "Q" + dates.quarter.astype(str),
        "MonthNo": dates.month,
        "MonthName": dates.strftime("%b"),
        "MonthYear": dates.strftime("%b-%Y"),
        "YearMonthSort": dates.year * 100 + dates.month,
        "WeekStart": (dates - pd.to_timedelta(dates.dayofweek, "D")).date,
        "DayOfWeekNo": dates.dayofweek + 1,
        "DayName": dates.strftime("%a"),
        "IsWeekend": (dates.dayofweek >= 5).astype(int),
    })

    # --- write
    fmt = "%Y-%m-%d %H:%M:%S"
    fact.to_csv(out / "FactTickets.csv", index=False, date_format=fmt)
    PRIORITIES.to_csv(out / "DimPriority.csv", index=False)
    TEAMS.to_csv(out / "DimTeam.csv", index=False)
    agents.drop(columns=["_speed", "_reopen"]).to_csv(out / "DimAgent.csv", index=False)
    cats.drop(columns=["_w", "_pmix", "_cx", "TeamKey"]).to_csv(out / "DimCategory.csv", index=False)
    dim_date.to_csv(out / "DimDate.csv", index=False)
    pd.DataFrame({"AsOfDateTime": [AS_OF]}).to_csv(out / "DimSnapshot.csv", index=False, date_format=fmt)
    print(f"Wrote {n:,} tickets to {out.resolve()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data"))
    a = ap.parse_args()
    main(a.seed, a.out)
