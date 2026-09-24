# SLA Monitoring Agent: Step-by-Step Guide

Everything is in `Downloads\sla-monitoring-agent\sla-monitoring-agent\`:

| File / folder | What it is |
|---|---|
| **SLA_Dashboard.pbix** | The finished Power BI dashboard (5 pages, data already loaded). Open this. |
| **run_dashboard.bat** + `app\` | The same dashboard as a Python web app, plus the **✦ AI Agent** tab |
| `app\agent\` + `run_agent_chat.bat`, `run_daily_report.bat`, `schedule_daily_report.bat`, `setup_ai_key.bat` | The AI agent (Part D) |
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

This is the same dashboard as a web app. It looks exactly like the design picture, and the last tab is the **✦ AI Agent** (Part D).

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
| `app\metrics.py` | The SLA engine: every KPI, the breakdowns, open-ticket queue, ticket lookup. Same definitions as the DAX. **The agent's tools call these functions.** |
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
| AI Agent badge still says *offline* | Check that `app\.env` (not `.env.example`) has `LLM_API_KEY=...`, save it, then restart `run_dashboard.bat` |
| `doctor` says `HTTP 401` | The key is wrong or was deleted. Create a new one |
| `doctor` says `HTTP 429` | Free-tier rate limit. Wait a minute. The agent answers offline meanwhile |
| E-mail `failed: SMTPAuthenticationError` | Use a Gmail **App Password**, not your normal password |
| `No module named sklearn` | Run `run_dashboard.bat` once; it installs the new packages |

---

## Part D: The AI agent (Phase 2)

### D1. What it is
The agent watches the SLA data and does four jobs a service-delivery manager would do every morning:

| Job | What happens | Where the code is |
|---|---|---|
| **Monitor** | Health check covering the last 30 days vs target and vs the previous 90 days, every team, the live queue, and the known risk patterns. Alerts are ranked critical / warning / info. | `app\agent\analysis.py` → `health_check()` |
| **Explain** | Automatic root cause: drills down level by level into the segment with the most *excess breaches* (breaches above what the average rate predicts). | `analysis.py` → `root_cause()` |
| **Predict** | ML model (gradient boosting) scores every open ticket for breach risk and says why. Tested on the last 60 days: ROC AUC 0.78. | `app\agent\predictor.py` |
| **Report & answer** | Writes the daily report, e-mails or posts it, and answers questions in plain English. | `core.py`, `report.py`, `notify.py`, `offline.py`, `llm.py` |

### D2. How a question is answered (the agent loop)
1. You ask: *"Why is Network Ops breaching?"*
2. `core.py` sends the question to the LLM with a system prompt (today's date, teams, SLA policy, rules) and the **11 tool definitions** from `tools.py`.
3. The LLM answers with a *tool call*, for example `root_cause(team="Network Ops")`.
4. Python runs that tool with pandas and returns the JSON result to the LLM.
5. The LLM may call more tools, such as `compare_periods` or `find_outliers`, up to 6 steps, and then writes the answer: headline, evidence and recommended actions.
6. The web page shows the answer and the tools used.

**No API key, or the internet is down?** The agent switches to **offline mode**. `offline.py` recognises the question type from keywords, pulls out the team, priority, agent and month, runs the same tools and fills an answer template. So the agent always works.

The LLM never does the maths. All numbers come from the same pandas code as the dashboard, so the agent and the dashboards always agree.

### D3. Set it up (10 minutes)
1. **Start it:** double-click `run_dashboard.bat`. It installs scikit-learn the first time, which takes about a minute. Open the **✦ AI Agent** tab (last tab at the bottom). The badge says *offline (rule-based)*.
2. **Add a free LLM (recommended):** double-click `setup_ai_key.bat`.
   - The Groq console opens. Sign in with Google, then click **Create API Key** and copy it.
   - Notepad opens `app\.env`. Paste the key after `LLM_API_KEY=` and save.
   - Close the dashboard window and run `run_dashboard.bat` again. The badge now says **groq · llama-3.3-70b-versatile**.
   - Check it: open a terminal in `app\` and run `.venv\Scripts\python run_agent.py doctor`. It should say `LLM test: OK`.
   - Prefer Google? Set `LLM_PROVIDER=gemini` and use a key from aistudio.google.com/apikey.
3. **E-mail the report (optional):** in `app\.env` fill `SMTP_USER` (your Gmail), `SMTP_PASSWORD` and `ALERT_EMAIL_TO`. For the password, use a Gmail *App Password*: myaccount.google.com → Security → 2-Step Verification → App passwords. Don't use your normal password.
4. **Slack / Teams alert (optional):** paste an incoming-webhook URL into `WEBHOOK_URL`.
5. **Automate it:** double-click `schedule_daily_report.bat` and enter a time (e.g. 09:00). Windows then runs the agent every day, saves `reports\sla_report_<date>.html` and sends it. The log goes to `reports\agent_log.txt`.

### D4. Use it every day
| Where | What to do |
|---|---|
| **✦ AI Agent tab** | Read *Today's briefing* (status, root cause, alerts) and the *Breach risk* table (click a ticket to open it). Ask questions in the chat or click a suggestion. Click **Generate daily report** to build and send the report. |
| `run_agent_chat.bat` | The same chat in a terminal window |
| `run_daily_report.bat` | Builds today's report and opens it in the browser |
| E-mail / Teams | The scheduled report arrives every morning |

Good demo questions for an interview:

- *How are we doing today?*
- *Why did SLA drop in March?* (answer: ERP surge → tickets reassigned 3+ times)
- *Which tickets will breach in the next 4 hours?*
- *Which agents need support?*
- *Why is Network Ops breaching?*
- *Compare August vs July*

### D5. How to explain it in an interview
> "I built an SLA monitoring agent for an IT service desk. A pandas metric engine feeds both a Power BI dashboard and a Flask app. On top of it, an LLM agent uses tool calling to answer questions like *why did SLA drop in March* by running a root-cause drill-down. It uses the same excess-breach logic as a decomposition tree, so every number is exact. A gradient-boosting model predicts which open tickets will breach (AUC 0.78 on a time-based holdout). Every morning it builds an HTML report with an executive summary and recommended actions and e-mails it. It runs on free models (Groq, Gemini or a local Ollama), falls back to a rule-based mode with no key, and it's covered by 18 automated tests, including a fake LLM server for the tool loop."

### D6. Tests
In `app\` with the venv active: `pip install pytest`, then `cd ..` and `python -m pytest -q`. You should see `18 passed`.

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
- Repo page → **Settings** → *General* → **Social preview** → *Edit* → upload `docs\images\social_preview.png`. This is the card people see when the link is shared on LinkedIn, WhatsApp or Slack.
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
