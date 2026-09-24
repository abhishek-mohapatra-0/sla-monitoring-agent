"""
SLA Monitoring Dashboard - web app.

Run:   python app.py        then open http://127.0.0.1:8050
Needs: pip install -r requirements.txt   (Flask + pandas, both free)
"""
import webbrowser
from threading import Timer

from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from agent import SLAAgent
from agent.config import REPORTS_DIR
from metrics import BREAKDOWN_DIMS, SLAData

app = Flask(__name__)
DATA = SLAData()
AGENT = SLAAgent(DATA)          # Phase 2: the AI agent shares the same data + metric engine
_BRIEF = {}
PORT = 8050


def filters():
    a = request.args
    return {k: (a.get(k) or None) for k in ("start", "end", "priority", "team", "channel")}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/meta")
def meta():
    return jsonify({
        "as_of": DATA.as_of.strftime("%d %b %Y, %H:%M"),
        "min_date": DATA.min_date.strftime("%Y-%m-%d"),
        "max_date": DATA.max_date.strftime("%Y-%m-%d"),
        "teams": DATA.teams, "priorities": DATA.priorities, "channels": DATA.channels,
        "breakdown_dims": list(BREAKDOWN_DIMS),
    })


@app.route("/api/overview")
def overview():
    return jsonify(DATA.overview(**filters()))


@app.route("/api/queue")
def queue():
    return jsonify(DATA.queue(**filters()))


@app.route("/api/people")
def people():
    return jsonify(DATA.people(agent=request.args.get("agent") or None, **filters()))


@app.route("/api/rootcause")
def rootcause():
    return jsonify(DATA.rootcause(**filters()))


@app.route("/api/breakdown")
def breakdown():
    raw = request.args.get("path", "")
    path = [tuple(p.split(":", 1)) for p in raw.split("|") if ":" in p]
    dim = request.args.get("dim", "Team")
    if dim not in BREAKDOWN_DIMS:
        abort(400)
    return jsonify(DATA.breakdown(path=path, dim=dim, **filters()))


@app.route("/api/ticket/<ticket_id>")
def ticket(ticket_id):
    t = DATA.ticket(ticket_id.strip().upper())
    return jsonify(t) if t else (jsonify({"error": "not found"}), 404)


# ------------------------------------------------------------------ AI agent
@app.route("/api/agent/status")
def agent_status():
    return jsonify({"mode": AGENT.mode, "llm": AGENT.llm is not None})


@app.route("/api/agent/chat", methods=["POST"])
def agent_chat():
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()[:2000]
    if not msg:
        return jsonify({"error": "empty message"}), 400
    return jsonify(AGENT.chat(msg, body.get("history") or []))


@app.route("/api/agent/briefing")
def agent_briefing():
    if "h" not in _BRIEF:                       # data is a daily snapshot: compute once per run
        _BRIEF["h"] = AGENT.briefing()
    return jsonify(_BRIEF["h"])


@app.route("/api/agent/risk")
def agent_risk():
    return jsonify(AGENT.get_predictor().top_risk(limit=int(request.args.get("limit", 15))))


@app.route("/api/agent/report", methods=["POST"])
def agent_report():
    send = request.args.get("send") == "1"
    rep = AGENT.daily_report(send=send)
    name = Path(rep["html_path"]).name
    return jsonify({"subject": rep["subject"], "file": name, "html_url": f"/reports/{name}",
                    "sent": rep["sent"] if send else {}})


@app.route("/reports/<path:name>")
def reports(name):
    return send_from_directory(REPORTS_DIR, name)


if __name__ == "__main__":
    from threading import Thread
    Thread(target=AGENT.get_predictor, daemon=True).start()     # warm up the ML model
    Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"\n  SLA dashboard + AI agent running at http://127.0.0.1:{PORT}   (Ctrl+C to stop)")
    print(f"  Agent mode: {AGENT.mode}\n")
    app.run(host="127.0.0.1", port=PORT, debug=False)
