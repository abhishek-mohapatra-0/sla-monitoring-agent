"""
SLA Monitoring Dashboard - web app.

Run:   python app.py        then open http://127.0.0.1:8050
Needs: pip install -r requirements.txt   (Flask + pandas, both free)
"""
import webbrowser
from threading import Timer

from flask import Flask, abort, jsonify, render_template, request

from metrics import BREAKDOWN_DIMS, SLAData

app = Flask(__name__)
DATA = SLAData()
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


if __name__ == "__main__":
    Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"\n  SLA dashboard running at http://127.0.0.1:{PORT}   (Ctrl+C to stop)\n")
    app.run(host="127.0.0.1", port=PORT, debug=False)
