# SLA Dashboard: Power BI Build Guide

Target: a 5-page Power BI report on 61,884 synthetic IT tickets (Sep 2025 – Sep 2026).
Canvas: 16:9 (1280 × 720). Theme: `SLA_Theme.json`. Measures: `DAX_Measures.dax`.
See `mockup_overview.png` for the Overview page layout.

---

## 1. Load the data (Power Query)

Get Data → Text/CSV → load all 7 files from `/data`. In Power Query set these types:

| Table | Column(s) | Type |
|---|---|---|
| FactTickets | CreatedDateTime, FirstResponseDateTime, ResolvedDateTime, ResponseDueDateTime, ResolutionDueDateTime | Date/Time |
| FactTickets | CreatedDate, ResolvedDate | Date |
| FactTickets | ResponseMinutes, ResolutionHours | Decimal |
| FactTickets | ResponseSLAMet, ResolutionSLAMet, CSATScore, IsOpen, Reopened, ReassignmentCount, *Key columns | Whole number |
| DimDate | Date, WeekStart | Date |
| DimSnapshot | AsOfDateTime | Date/Time |
| DimPriority | ComplianceTarget | Percentage |

Blank cells in the SLA/CSAT columns must stay **null**, not 0. They mean "open and not yet due" or "no survey".

## 2. Data model (star schema)

```
            DimPriority   DimTeam   DimAgent   DimCategory
                  \          |         |          /
                   \         |         |         /
DimDate ──(active: CreatedDate)── FactTickets
        ╌╌(inactive: ResolvedDate)╌╌╯
DimSnapshot  (no relationship: holds the "as of" timestamp)
```

- All relationships are **one-to-many, single direction** (dimension → fact).
- `DimDate[Date]` → `FactTickets[CreatedDate]` is **active**; `→ FactTickets[ResolvedDate]` is **inactive** (used by `USERELATIONSHIP` in *Tickets Resolved (Resolved Date)*).
- Do **not** relate DimAgent to DimTeam. The fact table already carries TeamKey, and a second path would make the model ambiguous.
- DimDate: *Mark as date table* on `Date`. Sort `MonthYear` by `YearMonthSort`, and `DayName` by `DayOfWeekNo`.
- DimPriority: sort `Priority` by `SortOrder`.
- Hide all key columns and the raw 0/1 flag columns from report view.

## 3. Measures

Create an empty `_Measures` table and paste in the measures from `DAX_Measures.dax`. Add the calculated columns at the top of that file to FactTickets. Set formats:

- `%` measures: Percentage, 1 decimal
- `(hrs)` / `(mins)`: Decimal, 1 decimal
- counts: Whole number, thousands separator

**Expected values with no filters** (use these to check your build):

| Measure | Value |
|---|---|
| Total Tickets | 61,884 |
| Resolution SLA % | 88.9% |
| SLA Target % | 91.8% |
| Response SLA % | 87.1% |
| Breached Tickets | 6,871 |
| Open Tickets | 196 (26 overdue, 3 at risk) |
| MTTR (hrs) | 21.4 |
| MTTA (mins) | 141.5 |
| Avg CSAT | 4.04 |
| Reopen Rate % | 4.3% |

## 4. Design rules (apply on every page)

- **Layout grid:** 16 px outer margin, 10 px gaps. Row 1 has the title plus slicers, row 2 the KPI cards, rows 3–4 the charts.
- **Colour:** Series colours come from the theme in fixed order (blue = primary measure, orange = comparison). Red, amber and green are **reserved for SLA status only**, never for a series.
- **Status is never colour alone:** always show the icon and label (`▲ On target`, `● Watch`, `▼ Below target`) using the *SLA Status Icon* / *SLA Status* measures.
- **Targets are drawn as references,** not extra bars: a dashed target line on trends (add *SLA Target %* as a second line and format it dashed grey), and a target tick on bar charts (Analytics pane → constant line, or a bullet-style error bar).
- **One y-axis per chart.** Never put SLA % and ticket counts on a dual axis; use two visuals instead.
- **Data labels:** only on the latest point and the notable outlier, not on every point.
- Put every slicer in the top row, and sync them across pages (View → Sync slicers).
- Show the *As Of Label* measure in a small card under each page title.

---

## 5. Pages

### Page 1: Overview (for managers, answers "are we meeting SLA?")
Mockup: `mockup_overview.png`

| Position | Visual | Fields |
|---|---|---|
| Top-right | 4 slicers (dropdown) | DimDate[Date] (relative: last 12 months), DimPriority[Priority], DimTeam[Team], FactTickets[Channel] |
| KPI row | 6 cards (new Card visual, with reference labels) | Resolution SLA % (reference label: *KPI Subtitle SLA*) · Response SLA % (ref: Response Breaches) · Total Tickets (ref: Breached Tickets) · Open Tickets (ref: Overdue Open Tickets, At-Risk Tickets) · MTTR (hrs) (ref: MTTA) · Avg CSAT (ref: Reopen Rate %) |
| Mid-left (wide) | Line chart | X: DimDate[MonthYear]; Y: Resolution SLA %, SLA Target % (dashed) |
| Mid-right | Clustered bar | Y: DimPriority[PriorityShort]; X: Resolution SLA %; target tick per priority; data labels on |
| Bottom-left | Clustered column | X: MonthYear; Y: Total Tickets, Tickets Resolved (Resolved Date) |
| Bottom-right | Table "Team scorecard" | Team, Total Tickets, Resolution SLA %, SLA Target %, SLA Gap (pts) with icon conditional formatting, MTTR, Multi-Hop %; sort by Gap ascending |

### Page 2: Live Queue (for team leads, answers "what needs attention now?")

| Visual | Fields / notes |
|---|---|
| KPI cards | Open Tickets · Overdue Open Tickets · At-Risk Tickets · Avg Open Age (hrs) |
| Stacked bar "Open by SLA status" | Y: Team; X: Open Tickets; Legend: SLAStatus (only the Open- values). Colour: Overdue = critical red, At Risk = amber, On Track = blue |
| Column chart "Backlog ageing" | X: Backlog Age Bucket (sorted by Backlog Age Sort); Y: Open Tickets |
| Table "Tickets to action" | TicketID, Priority, Team, Agent, Status, CreatedDateTime, Hours To Breach. Filter IsOpen = 1; sort Hours To Breach ascending; conditional font colour red when < 0 |
| Donut? **No.** | Use the stacked bar above. Donuts are hard to compare |

### Page 3: Team & Agent Performance (answers "who needs support?")

| Visual | Fields / notes |
|---|---|
| Matrix | Rows: Team → AgentName (drill); Values: Total Tickets, Resolution SLA %, MTTR, Avg Reassignments, Reopen Rate %, Avg CSAT, Agent SLA Rank. Data bars on Total Tickets; icons on SLA % |
| Scatter | X: Total Tickets; Y: Resolution SLA %; Details: AgentName; Legend: Team (limit to the selected team, since more than 3 colours in a scatter is hard to read). A constant line at SLA Target % |
| Line chart | Resolution SLA % by MonthYear for the agent picked in the matrix (edit interactions: matrix filters this chart) |
| Card + tooltip page | Agent tooltip: tickets, SLA %, reopen rate, hire date |

What you should find here: one Application Support agent with ~64% SLA and MTTR ~35 h (team average ~84%), and a new Service Desk joiner (hired Jun 2026) with a ~17% reopen rate (team average ~4%).

### Page 4: Breach Root Cause (answers "why are we breaching?")

| Visual | Fields / notes |
|---|---|
| Decomposition tree | Analyse: Breached Tickets; Explain by: Team, Priority, SubCategory, Reassignment Band, Shift, Channel, DayName |
| Key influencers | Analyse: FactTickets[SLAStatus] = "Breached"; Explain by: Team, Priority, SubCategory, ReassignmentCount, Shift, DayName, Channel |
| Column chart | X: Reassignment Band; Y: Breach Rate %. Breach rate climbs from ~6% (0 hand-offs) to ~83% (3+) |
| Matrix heatmap | Rows: DayName; Columns: CreatedHour; Values: Response SLA % with a single-hue blue background scale (light = low). This shows the overnight and weekend gap |
| Line chart | Resolution SLA % 30D rolling, with a text box annotating the March 2026 ERP migration surge |

What you should find here: Network Ops P2 tickets breach heavily because of repeated reassignment; P3 tickets logged at night (20:00–08:00) miss the response SLA because there is no night cover; weekends respond more slowly; and March 2026 has a volume spike with an SLA dip.

### Page 5: Ticket Detail (drill-through)

- Drill-through field: FactTickets[TicketID] (also allow drill from Team and Agent).
- Cards: Priority, Team, Agent, Status, SLAStatus.
- Timeline table: Created → Response due → First response → Resolution due → Resolved.
- Multi-row card: ReassignmentCount, Reopened, CSATScore.
- Back button, top-left.

---

## 6. Finishing touches

- Page navigator (Insert → Buttons → Navigator → Page navigator) in a left rail or top bar.
- Tooltips: build one tooltip page (320 × 240) showing SLA %, MTTR and ticket count, and assign it to the charts.
- Bookmarks: "Reset filters" button.
- Performance: use Performance Analyzer. Every visual should render in under 500 ms on 62k rows.
- Portfolio: export PDF screenshots of each page, record a 2-minute walkthrough, and push the `.pbix`, the `/data` folder and this guide to GitHub.

## 7. How this connects to the agent (next phase)

The same tables feed the SLA agent. Its tools will compute these measures in Python (pandas/DuckDB), detect when *Resolution SLA %* drops below *SLA Target %*, run the root-cause breakdown from Page 4 automatically, and write the daily summary. Re-run `scripts/generate_tickets.py` with a new `AS_OF` date to simulate new days of data.
