# SLA Daily Report · 2026-09-22

*Data as of 2026-09-22 18:00 · window 2026-08-24 to 2026-09-22 · summary by offline template*

## Executive summary

**Resolution SLA is 90.0% against a 91.8% target (Watch, -1.8 pts) over the last 30 days.**

- Versus the previous 90 days: 90.0% (+0.0 pts); 440 resolution breaches on 4,557 tickets.
- Main driver: Team Network Ops (21.6% breach rate) → Reassignments 3+ (80.3% breach rate).
- Network Ops below target: 78.4% vs 92.4%. Gap -14.1 pts on 656 tickets, 136 breaches.
- 26 open tickets already breached. Most in Application Support (13), Service Desk (10), Network Ops (2).
- People: Swati Singh (Application Support) resolves 64.3% in SLA; Deepak Hegde (Service Desk) reopen rate 17.1%.
- 8 open tickets have a high predicted breach risk, led by INC1061776 (74%), INC1061783 (74%), INC1061600 (68%).

**Recommended actions**
1. Escalate the overdue tickets to team leads today.
2. Daily breach review with the Network Ops lead; fix routing so tickets reach the right resolver group first time (assignment rules / skills-based routing).
3. 1:1 coaching and QA review for the flagged agents.

## Key numbers (last 30 days)

| Metric | Now | Previous 90 days |
|---|---|---|
| Resolution SLA | 90.0% (target 91.8%, Watch) | 90.0% |
| Response SLA | 87.3% | 87.6% |
| Tickets / breaches | 4,557 / 440 | 14,419 / 1,449 |
| MTTR | 19.83 h | 20.85 h |
| CSAT · reopen | 4.06 · 4.7% | 4.07 · 4.6% |
| Open now | 196 (26 overdue, 3 at risk) | |

## Alerts (2 critical, 9 warning, 1 info)

- **[CRITICAL] Network Ops below target: 78.4% vs 92.4%**: Gap -14.1 pts on 656 tickets, 136 breaches.
- **[CRITICAL] 26 open tickets already breached**: Most in Application Support (13), Service Desk (10), Network Ops (2).
- **[WARNING] Resolution SLA 90.0% vs target 91.8% (last 30 days)**: Gap -1.8 pts. Previous 90 days: 90.0% (+0.0 pts).
- **[WARNING] Application Support below target: 87.8% vs 91.9%**: Gap -4.1 pts on 1,177 tickets, 138 breaches.
- **[WARNING] 6 tickets will breach in the next 4 hours**: INC1061789, INC1061869, INC1061714, INC1061812, INC1061815.
- **[WARNING] Swati Singh (Application Support) resolves 64.3% in SLA**: Team peers: 86.4% (-22.1 pts); MTTR 35.3 h vs 21.6 h.
- **[WARNING] Deepak Hegde (Service Desk) reopen rate 17.1%**: New joiner, 3.7 months tenure; overall reopen rate 4.3%. Suggest coaching / QA review.
- **[WARNING] Night-shift P3 tickets miss response SLA 81.8% of the time**: Tickets logged 20:00-08:00 wait for the day shift.
- **[WARNING] Night-shift P4 tickets miss response SLA 60.4% of the time**: Tickets logged 20:00-08:00 wait for the day shift.
- **[WARNING] Weekend tickets miss response SLA 23.3% of the time**: Lower weekend staffing.
- **[WARNING] Reassignments drive breaches: 5.5% with 0 hand-offs vs 82.7% with 3+**: Most reassigned team: Network Ops (24.2% of tickets hop 2+ times).
- **[INFO] 2026-03: volume spike 6,586 vs 4,730 typical**: SLA fell to 76.8% (-13.5 pts); driven by ERP (SAP) (25.8% of that month's tickets).

## Root cause (last 30 days)

1. Team = **Network Ops**: 21.6% breach rate, 2.16x the level above, 30.9% of breaches
2. Reassignments = **3+**: 80.3% breach rate, 3.71x the level above, 12.0% of breaches

## Open tickets most likely to breach

| Ticket | Priority | Team | Agent | Hours left | Risk | Why |
|---|---|---|---|---|---|---|
| INC1061776 | P3 | Network Ops | Kunal Pillai | 17.2 | 74% | reassigned 3+ times (83% breach history); Network Ops (20% breach history); VPN (20% breach history) |
| INC1061783 | P3 | Network Ops | Nisha Das | 17.5 | 74% | reassigned 3+ times (83% breach history); agent Nisha Das (21% breach history); Network Ops (20% breach history) |
| INC1061600 | P4 | Application Support | Swati Singh | 43.1 | 68% | reassigned 2 times (41% breach history); agent Swati Singh (36% breach history) |
| INC1061815 | P2 | Network Ops | Yash Patel | 3.6 | 67% | reassigned 3+ times (83% breach history); agent Yash Patel (21% breach history); Network Ops (20% breach history) |
| INC1061812 | P2 | Application Support | Aarav Gupta | 3.5 | 56% | reassigned 2 times (41% breach history); P2 (20% breach history); ERP (SAP) (31% breach history) |
| INC1061751 | P3 | Application Support | Swati Singh | 15.1 | 55% | agent Swati Singh (36% breach history); ERP (SAP) (31% breach history) |
| INC1061618 | P4 | Application Support | Harsh Shetty | 44.0 | 54% | reassigned 2 times (41% breach history); ERP (SAP) (31% breach history) |
| INC1061757 | P3 | Application Support | Harsh Shetty | 15.5 | 53% | reassigned 2 times (41% breach history); ERP (SAP) (31% breach history) |

*Breach-risk model: gradient boosting, ROC AUC 0.776, PR AUC 0.447 (base rate 10.1%) on 2026-07-24 to 2026-09-22.*