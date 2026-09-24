"""
Tests for the SLA Monitoring Agent.   Run from the project folder:
    pip install pytest
    python -m pytest -q
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from agent import SLAAgent                   # noqa: E402
from agent.llm import LLMClient              # noqa: E402


@pytest.fixture(scope="session")
def agent():
    a = SLAAgent()
    a.llm = None            # tests run offline unless they plug in a fake LLM
    return a


# ------------------------------------------------------------------ analytics
def test_kpis_match_dashboard(agent):
    k = agent.tools.get_kpis()
    assert k["total"] == 61884
    assert k["res_sla"] == pytest.approx(0.889, abs=0.001)
    assert k["breaches"] == 6871 and k["open"] == 196


def test_health_check_finds_all_planted_patterns(agent):
    h = agent.briefing()
    text = " ".join(a["title"] + " " + a["detail"] for a in h["alerts"])
    assert "Swati Singh" in text                     # slow agent
    assert "Deepak Hegde" in text                    # new joiner, high reopen
    assert "Night-shift P3" in text                  # night response breaches
    assert "Weekend" in text                         # weekend effect
    assert "Reassignments drive breaches" in text    # hand-offs
    assert "2026-03" in text and "ERP (SAP)" in text  # March surge
    assert h["status"] in ("On target", "Watch", "Below target")


def test_root_cause_march_is_erp(agent):
    rc = agent.tools.root_cause(start="2026-03-01", end="2026-03-31")
    assert rc["path"][0]["value"] == "ERP (SAP)"


def test_root_cause_network_ops_p2_points_to_reassignments(agent):
    rc = agent.tools.root_cause(team="Network Ops", priority="P2")
    assert rc["path"][0]["dimension"] == "Reassignments"


def test_breach_model_is_useful(agent):
    m = agent.get_predictor().metrics
    assert m["roc_auc"] > 0.7
    top = agent.tools.predict_breach_risk(limit=5)["tickets"]
    assert len(top) == 5 and all(0 <= t["breach_risk"] <= 1 for t in top)


def test_bad_tool_input_returns_error_not_crash(agent):
    assert "error" in agent.tools.call("get_kpis", {"team": "Nope Team"})
    assert "error" in agent.tools.call("does_not_exist", {})


# ------------------------------------------------------------------ offline mode
@pytest.mark.parametrize("q, tool", [
    ("How are we doing today?", "health_check"),
    ("Why did SLA drop in March?", "root_cause"),
    ("Which tickets will breach next?", "predict_breach_risk"),
    ("Which agents need support?", "find_outliers"),
    ("What is Network Ops P2 SLA last month?", "get_kpis"),
    ("Compare August vs July", "compare_periods"),
    ("Tell me about INC1059600", "get_ticket"),
])
def test_offline_router(agent, q, tool):
    r = agent.chat(q)
    assert r["mode"] == "offline"
    assert tool in [t["tool"] for t in r["tools"]]
    assert len(r["answer"]) > 40


def test_offline_march_answer_mentions_erp(agent):
    assert "ERP (SAP)" in agent.chat("Why did SLA drop in March?")["answer"]


# ------------------------------------------------------------------ LLM tool loop (fake OpenAI-compatible server)
class FakeLLM(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeLLM.calls.append(body)
        if not any(m["role"] == "tool" for m in body["messages"]):
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "root_cause", "arguments": json.dumps({"start": "2026-03-01", "end": "2026-03-31"})}}]}
        else:
            tool_msg = [m for m in body["messages"] if m["role"] == "tool"][-1]
            top = json.loads(tool_msg["content"])["path"][0]["value"]
            msg = {"role": "assistant", "content": f"**March SLA fell because of {top} tickets.**"}
        out = json.dumps({"choices": [{"message": msg}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_llm_tool_calling_loop(agent):
    srv = HTTPServer(("127.0.0.1", 0), FakeLLM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        agent.llm = LLMClient(f"http://127.0.0.1:{srv.server_port}/v1", "fake-model", "test-key")
        r = agent.chat("Why did SLA drop in March?")
        assert "ERP (SAP)" in r["answer"]
        assert r["tools"][0]["tool"] == "root_cause"
        first = FakeLLM.calls[0]
        assert first["tools"] and first["messages"][0]["role"] == "system"
    finally:
        agent.llm = None
        srv.shutdown()


def test_llm_down_falls_back_to_offline(agent):
    agent.llm = LLMClient("http://127.0.0.1:9/v1", "x", "k", timeout=2)
    try:
        r = agent.chat("Which agents need support?")
        assert r["mode"] == "offline (fallback)" and "Swati Singh" in r["answer"]
    finally:
        agent.llm = None


# ------------------------------------------------------------------ report + web API
def test_daily_report_files(agent):
    rep = agent.daily_report(send=False)
    assert Path(rep["html_path"]).exists() and Path(rep["md_path"]).exists()
    assert "Recommended actions" in rep["summary"]


def test_web_api():
    import app as webapp
    webapp.AGENT.llm = None
    c = webapp.app.test_client()
    assert c.get("/api/agent/status").json["llm"] is False
    r = c.post("/api/agent/chat", json={"message": "Which tickets will breach next?"})
    assert r.status_code == 200 and "breach" in r.json["answer"].lower()
    assert c.get("/api/agent/briefing").json["alerts"]
    assert len(c.get("/api/agent/risk?limit=3").json["tickets"]) == 3
