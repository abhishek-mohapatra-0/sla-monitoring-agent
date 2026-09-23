# SLA Dashboard: Step-by-Step Guide

Everything is in `Downloads\sla-monitoring-agent\sla-monitoring-agent\`:

| File / folder | What it is |
|---|---|
| **SLA_Dashboard.pbix** | The finished Power BI dashboard (5 pages, data already loaded). Open this. |
| **run_dashboard.bat** + `app\` | The same dashboard as a Python web app (exact look of the design picture, live filters) |
| SLA_Dashboard.pbip + `.Report` + `.SemanticModel` folders | The same report as a *Power BI Project* (plain-text files, good for GitHub) |
| `data\` | The 7 CSV files the dashboard reads |
| `powerbi\DAX_Measures.dax` | Every measure and calculated column, with comments |
| `powerbi\SLA_Theme.json` | The colour theme |
| `powerbi\BUILD_GUIDE.md` | The design spec (pages, visuals, expected numbers) |
| `scripts\generate_tickets.py` | Regenerates the data |

---

## Part A: Use the finished dashboard (10 minutes)

**Step 1: Open it.** Double-click `SLA_Dashboard.pbix`. It opens on the **Overview** page with data already loaded.

**Step 2: Check the numbers.** With no filters applied you should see:
Resolution SLA **88.9%** (target 91.8%, status *Watch*), Response SLA **87.1%**, **61,884** tickets, **196** open (26 overdue, 3 at risk), MTTR **21.4 h**, CSAT **4.04**.

**Step 3: Refresh (only if you move the folder).** The data path is stored in a parameter.
If you move the project, go to Home → Transform data ▾ → **Edit parameters** → set `DataFolder` to the new `...\data\` path (keep the trailing `\`) → OK → **Refresh**.

**Step 4: Walk through the 5 pages.**
Use the **navigation bar at the top of every page**. In Power BI Desktop you are in edit mode, so hold **Ctrl** and click a button (or switch to View → Reading view and just click). After publishing to the Power BI Service, a normal click works.
Filters (Date, Priority, Team, Channel) sit in the top-right of each page and only affect that page.


| Page | Question it answers | Try this |
|---|---|---|
| Overview | Are we meeting SLA? | Pick *Network Ops* in the Team slicer and watch every visual react |
| Live Queue | What needs attention right now? | The table is sorted by *Hours To Breach*. Negative means already breached |
| Team & Agent | Who needs support? | The **Agent leaderboard** lists the weakest agents first (Swati Singh at ~64%). Click a name to see that agent's reopen trend; click **+** in the scorecard to expand a team |
| Breach Root Cause | Why are we breaching? | In the decomposition tree click **+** → Team → Network Ops → **+** → PriorityShort → P2 → **+** → Reassignment Band |
| Ticket Detail | Everything about one ticket | On Live Queue, right-click a ticket row → **Drill through → Ticket Detail**. Opening it from the nav bar shows the first ticket only |

**Step 5: Find the 6 built-in problems.** Being able to explain these is what makes the project interview-ready:

1. Network Ops P2 tickets breach heavily because they're reassigned repeatedly (breach rate goes from 6% with 0 hand-offs to 83% with 3+).
2. One Application Support agent sits at ~64% SLA against a team average of ~84%.
3. A Service Desk new joiner (hired Jun 2026) has a ~17% reopen rate.
4. P3 tickets logged at night (20:00–08:00) miss the response SLA, which shows as the dark columns in the heatmap.
5. Weekends respond more slowly (the Sat/Sun rows in the heatmap).
6. In March 2026 an ERP migration surge causes a volume spike and an SLA dip to about 77%.

**Step 6: Make it portfolio-ready.**
- File → Export → **Export to PDF** to get one image per page.
- Record a 2-minute screen video walking through Step 5.
- Publish it to GitHub with one click (see **Part E**). The `.pbip` text files let reviewers read your model and DAX.
- Optional: publish to the Power BI Service (needs a work/school account) and share the link.

---

## Part A2: Run the Python web dashboard (5 minutes)

This is the same dashboard as a web app. It looks exactly like the design picture, and Phase 2 (the agent) will be added to it.

**Option 1: one click**
1. Double-click `run_dashboard.bat`.
2. The first run creates a virtual environment in `app\.venv` and installs Flask + pandas (about 1 minute, internet needed once).
3. Your browser opens **http://127.0.0.1:8050**. Close the black window (or press Ctrl+C) to stop it.

**Option 2: VS Code**
1. File → Open Folder → `sla-monitoring-agent`.
2. Open a terminal (Ctrl+`) and run:
   ```
   cd app
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
3. Next time: open `app\app.py`, pick the `.venv` interpreter (bottom-right of VS Code), and press **F5** → *Python File*.

**What's in the app**

| File | Role |
|---|---|
| `app\metrics.py` | The SLA engine: every KPI, the breakdowns, open-ticket queue, ticket lookup. Same definitions as the DAX. **The agent will call these functions.** |
| `app\app.py` | Flask web server with JSON endpoints (`/api/overview`, `/api/queue`, `/api/people`, `/api/rootcause`, `/api/breakdown`, `/api/ticket/<id>`) |
| `app\templates\index.html` | Page layout |
| `app\static\style.css` · `charts.js` · `app.js` | Styling, hand-built SVG charts (no chart library), page logic |

Things to try: pick *Network Ops* in the Team filter; click a team row in the scorecard; on **Breach Root Cause** click *Network Ops* → *P2* in the bars to drill down; on **Live Queue** click any ticket row.

Check the numbers match Power BI: 88.9% Resolution SLA, 87.1% Response SLA, 61,884 tickets, 196 open.

---

## Part B: Rebuild it yourself from scratch (the learning path)

Do this once. It turns "I have a dashboard" into "I can explain every design choice". Use a new blank report and keep the finished pbix open for reference.

### 1. Load the data
Home → Get data → **Text/CSV**. Load all 7 files in `data\`. Click **Transform data** and set types:
- All `...DateTime` columns → Date/Time; `CreatedDate`, `ResolvedDate`, `Date`, `WeekStart`, `HireDate` → Date
- `ResponseMinutes`, `ResolutionHours`, `ComplianceTarget` → Decimal
- Keys, flags, `ResponseSLAMet`, `ResolutionSLAMet`, `CSATScore`, counts → Whole number
- Blank cells must stay **null**. They mean "open and not due yet" or "no survey".

*Pro tip:* create a text parameter `DataFolder` and use `File.Contents(DataFolder & "FactTickets.csv")` so the path lives in one place.

### 2. Build the star schema (Model view)
- Drag `FactTickets[PriorityKey]` → `DimPriority[PriorityKey]`, and do the same for Team, Agent and Category (all one-to-many, single direction).
- `FactTickets[CreatedDate]` → `DimDate[Date]` (**active**).
- `FactTickets[ResolvedDate]` → `DimDate[Date]`, then set it to **inactive** (dotted line).
- Do **not** join DimAgent to DimTeam; it would create an ambiguous path.
- DimDate → Table tools → **Mark as date table**. Sort `MonthYear` by `YearMonthSort` and `DayName` by `DayOfWeekNo`. Sort `Priority` by `SortOrder`.
- File → Options → Current file → Data load → untick **Auto date/time**.

### 3. Add calculated columns and measures
- Home → Enter data → name it `_Measures` → Load. This becomes your measure table.
- Copy each measure from `powerbi\DAX_Measures.dax` (Home → New measure). Put them in display folders (1 Volume, 2 SLA, …).
- Add the 5 calculated columns to FactTickets (Table tools → New column).
- **Two lessons baked into this file:**
  - Use `==` not `=` when testing for 0. In DAX, `BLANK() = 0` is TRUE, so `= 0` counts open tickets as breaches (you'd get 7,041 instead of 6,871).
  - A sort-by column can't depend on the column it sorts. That's why *Backlog Age Sort* recalculates the age instead of reading *Backlog Age Bucket*.

### 4. Apply the theme and page style
View → Themes → **Browse for themes** → `powerbi\SLA_Theme.json`. Page size: View → Page view, then Format page → Canvas settings → 16:9 (1280 × 720).

### 5. Build the Overview page
1. Text box title (17pt bold) plus a **Card (new)** showing `As Of Label` (label off, value 10pt grey, no background).
2. Four slicers: Date (Between), Priority, Team, Channel (Dropdown). Header text in capitals, 8pt grey.
3. Six KPI tiles, each one **Card (new)** visual:
   - Data = the KPI measure (e.g. Resolution SLA %). Callout → Value 22pt bold; Label 10pt, position *Top*.
   - Reference labels → Add data → the matching `KPI Subtitle …` measure. Turn reference label **Title off**; Value 9pt, not bold.
   - Cards → Border off, Divider off, Background off, Padding 4px (the tile box comes from the visual border in the theme).
   - For the SLA tile: Reference labels → Value → Color → fx → Field value → `SLA Status Color`.
4. Line chart: X = **MonthLabel**, Y = Resolution SLA % and SLA Target %. Target line: Lines → stroke dashed. Subtitle "March dip = ERP migration surge".
5. **Line and clustered column** chart for the priority target ticks: X = PriorityShort, Column y = Resolution SLA %, Line y = SLA Target %. Then Lines → Target stroke width 0; Markers → on for all series → shape **long dash**, size 12–18, colour black. Data labels inside end, white. Secondary y-axis off and 0–100%.
6. Clustered column: MonthLabel vs Total Tickets and Tickets Resolved (Resolved Date), renamed Created / Resolved.
7. Table "Team scorecard": Team, Tickets, SLA %, Target, **SLA Gap Label** (font colour → fx → `SLA Status Color`), MTTR, Multi-hop; totals off.

### 6. Build the other pages
Follow the page tables in `powerbi\BUILD_GUIDE.md` §5. The key techniques:
- **Stacked bar** with Legend = SLAStatus, filtered to the three *Open* statuses.
- **Visual-level filter** IsOpen = 1 on the backlog chart and the action table.
- **Matrix** with Team → AgentName rows (drill with +).
- **Scatter**: X Total Tickets, Y SLA %, Values AgentName.
- **Decomposition tree**: Analyze = Breached Tickets, Explain by 7 fields.
- **Heatmap**: matrix with DayName × CreatedHour, values Response Breach %, background colour gradient.

### 7. Drill-through page
New page → add fields → in the Visualizations pane put `FactTickets[TicketID]` in **Drill through**. Power BI adds a back button automatically. Hide the page (right-click the tab → Hide page).

### 8. Save
File → Save as → **.pbix** (one file, easy to share) or **.pbip** (text files, good for Git).

---

## Part C: Troubleshooting

| Problem | Fix |
|---|---|
| "Couldn't find file ... FactTickets.csv" | Edit parameters → fix `DataFolder` (Part A, Step 3) |
| Dates look wrong / blank | Your Windows region uses a different date format. The queries force `en-US` parsing, so just Refresh |
| Numbers differ from Part A | You regenerated the data with a different seed or date. That's fine; the patterns will still be there |
| "One or more relationships need refresh" banner | Click **Refresh now** |

---

## Part D: What's next (Phase 2: the agent)

The agent reads the same CSVs and reproduces these measures in Python (pandas/DuckDB). It will:
1. check every morning whether *Resolution SLA %* is below *SLA Target %*,
2. run the same breakdown as the decomposition tree (Team → Priority → Reassignment Band …) to find the cause,
3. write a plain-English summary and send it as an alert,
4. answer questions like "why did SLA drop in March?".

The dashboard shows *what* is happening; the agent explains *why* and tells people.

---

## Part E: Publish to GitHub (one click, no Git install needed)

1. Double-click **`publish_to_github.bat`**. It opens GitHub's *New personal access token (classic)* page with the **repo** scope already ticked.
2. On that page, set Expiration to **7 days**, click **Generate token** at the bottom, and copy the token (starts with `ghp_`).
3. Go back to the black window and paste the token with right-click or Ctrl+V. It stays hidden while you paste. Press Enter.
4. Press Enter again to accept the name `sla-monitoring-agent`, and Enter once more for **public**.
5. The script creates the repo, uploads all the files in one commit (about 14 MB), adds the description and topics, and opens the repo in your browser.

The script never uploads `app\.venv`, Power BI cache files (`cache.abf`, `localSettings.json`), the `Claude outputs` folder or the publish scripts themselves. The token isn't saved anywhere.

**Changed something later?** Run the same bat again with a new token. It adds a new commit to the same repo.

**After publishing:**
- Your profile → **Customize your pins** → pin `sla-monitoring-agent`.
- Delete the token when you're done: github.com → Settings → Developer settings → Personal access tokens → Delete.

**Prefer Git?** Install Git for Windows, then run this in the project folder:
```
git init -b main
git add .
git commit -m "SLA Monitoring Agent"
git remote add origin https://github.com/<your-username>/sla-monitoring-agent.git
git push -u origin main
```
Create the empty repo on github.com first. The `.gitignore` already skips the right files.
