"""
Daily SLA report -> reports/sla_report_YYYY-MM-DD.md and .html

The HTML uses inline styles and tables only, so it looks the same in a browser
and inside Gmail / Outlook.
"""
from __future__ import annotations

import html
import re
from datetime import datetime

from .analysis import pct
from .config import REPORTS_DIR

SEV = {"critical": ("#d03b3b", "Critical"), "warning": ("#b07800", "Warning"),
       "info": ("#2a78d6", "Info"), "ok": ("#006300", "OK")}
STATUS_COLOR = {"On target": "#006300", "Watch": "#8a6100", "Below target": "#d03b3b"}


def md_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def md_to_html(md: str) -> str:
    """Just enough Markdown for summaries: headings, bullets, numbered lists, bold/italic."""
    out, lst = [], None
    for line in md.splitlines():
        t = line.strip()
        m_ul = re.match(r"^[-*•]\s+(.*)", t)
        m_ol = re.match(r"^\d+[.)]\s+(.*)", t)
        kind = "ul" if m_ul else "ol" if m_ol else None
        if lst and kind != lst:
            out.append(f"</{lst}>")
            lst = None
        if kind:
            if not lst:
                out.append(f'<{kind} style="margin:6px 0 10px 20px;padding:0">')
                lst = kind
            out.append(f'<li style="margin:3px 0">{md_inline((m_ul or m_ol).group(1))}</li>')
        elif t.startswith("#"):
            out.append(f'<p style="margin:10px 0 4px;font-weight:600">{md_inline(t.lstrip("#").strip())}</p>')
        elif t:
            out.append(f'<p style="margin:6px 0">{md_inline(t)}</p>')
    if lst:
        out.append(f"</{lst}>")
    return "\n".join(out)


def _tile(label, value, sub, color="#0b0b0b"):
    return (f'<td style="padding:4px"><div style="border:1px solid #e1e0d9;border-radius:8px;background:#fcfcfb;padding:10px 12px">'
            f'<div style="font-size:11px;color:#52514e">{label}</div>'
            f'<div style="font-size:22px;font-weight:700;color:{color}">{value}</div>'
            f'<div style="font-size:11px;color:#52514e">{sub}</div></div></td>')


def build_report(h: dict, summary: str, author: str, model_metrics: dict) -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    day = h["as_of"][:10]
    c, p = h["current"], h["previous"]
    risk = (h.get("at_risk_tickets") or {}).get("tickets") or []
    rc = h["root_cause"]["path"]
    delta = (c["res_sla"] - p["res_sla"]) * 100 if c["res_sla"] is not None and p["res_sla"] is not None else 0

    # ---------------- markdown
    md = [f"# SLA Daily Report · {day}", "",
          f"*Data as of {h['as_of']} · window {h['window']['start']} to {h['window']['end']} · summary by {author}*", "",
          "## Executive summary", "", summary, "",
          "## Key numbers (last %d days)" % h["window"]["days"], "",
          "| Metric | Now | Previous %d days |" % h["baseline"]["days"], "|---|---|---|",
          f"| Resolution SLA | {pct(c['res_sla'])} (target {pct(c['target'])}, {c['status']}) | {pct(p['res_sla'])} |",
          f"| Response SLA | {pct(c['resp_sla'])} | {pct(p['resp_sla'])} |",
          f"| Tickets / breaches | {c['total']:,} / {c['breaches']:,} | {p['total']:,} / {p['breaches']:,} |",
          f"| MTTR | {c['mttr_hrs']} h | {p['mttr_hrs']} h |",
          f"| CSAT · reopen | {c['csat']} · {pct(c['reopen_rate'])} | {p['csat']} · {pct(p['reopen_rate'])} |",
          f"| Open now | {c['open']} ({c['overdue']} overdue, {c['at_risk']} at risk) | |", "",
          f"## Alerts ({h['counts']['critical']} critical, {h['counts']['warning']} warning, {h['counts']['info']} info)", ""]
    md += [f"- **[{a['severity'].upper()}] {a['title']}**: {a['detail']}" for a in h["alerts"]]
    if rc:
        md += ["", "## Root cause (last %d days)" % h["window"]["days"], ""]
        md += [f"{i}. {x['dimension']} = **{x['value']}**: {pct(x['breach_rate'])} breach rate, {x['lift']}x the level above, "
               f"{pct(x['share_of_all_breaches'])} of breaches" for i, x in enumerate(rc, 1)]
    if risk:
        md += ["", "## Open tickets most likely to breach", "",
               "| Ticket | Priority | Team | Agent | Hours left | Risk | Why |", "|---|---|---|---|---|---|---|"]
        md += [f"| {t['ticket']} | {t['priority']} | {t['team']} | {t['agent']} | {t['hours_to_breach']} | "
               f"{pct(t['breach_risk'], 0)} | {'; '.join(t['why'])} |" for t in risk]
    md += ["", f"*Breach-risk model: gradient boosting, ROC AUC {model_metrics['roc_auc']}, "
               f"PR AUC {model_metrics['pr_auc']} (base rate {pct(model_metrics['base_rate'])}) on {model_metrics['test_period']}.*"]
    md_text = "\n".join(md)

    # ---------------- html
    sc = STATUS_COLOR.get(c["status"], "#0b0b0b")
    tiles = "".join([
        _tile("Resolution SLA", pct(c["res_sla"]), f"{c['status']} · {c['gap_pts']:+.1f} pts vs {pct(c['target'])}", sc),
        _tile("Response SLA", pct(c["resp_sla"]), f"{c['resp_breaches']:,} response breaches"),
        _tile("Tickets", f"{c['total']:,}", f"{c['breaches']:,} resolution breaches"),
        _tile("Open now", str(c["open"]), f"{c['overdue']} overdue · {c['at_risk']} at risk",
              "#d03b3b" if c["overdue"] else "#0b0b0b"),
        _tile("MTTR", f"{c['mttr_hrs']} h", f"MTTA {c['mtta_min']} min"),
    ])
    alert_rows = "".join(
        f'<tr><td style="padding:6px 8px;border-top:1px solid #eeede8;white-space:nowrap">'
        f'<span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;color:#fff;background:{SEV[a["severity"]][0]}">'
        f'{SEV[a["severity"]][1]}</span></td>'
        f'<td style="padding:6px 8px;border-top:1px solid #eeede8"><b>{html.escape(a["title"])}</b><br>'
        f'<span style="color:#52514e">{html.escape(a["detail"])}</span></td></tr>' for a in h["alerts"])
    rc_html = "".join(
        f'<td style="padding:4px"><div style="border:1px solid #e1e0d9;border-radius:8px;padding:8px 10px;background:#fcfcfb">'
        f'<div style="font-size:11px;color:#52514e">{i}. {html.escape(x["dimension"])}</div>'
        f'<div style="font-weight:700">{html.escape(x["value"])}</div>'
        f'<div style="font-size:12px;color:#d03b3b">{pct(x["breach_rate"])} breach rate</div>'
        f'<div style="font-size:11px;color:#52514e">{x["lift"]}× level above · {pct(x["share_of_all_breaches"])} of breaches</div></div></td>'
        + ('<td style="color:#52514e;font-size:18px">→</td>' if i < len(rc) else "") for i, x in enumerate(rc, 1))
    risk_rows = "".join(
        f'<tr><td style="padding:5px 8px;border-top:1px solid #eeede8"><b>{t["ticket"]}</b></td>'
        f'<td style="padding:5px 8px;border-top:1px solid #eeede8">{t["priority"]}</td>'
        f'<td style="padding:5px 8px;border-top:1px solid #eeede8">{html.escape(t["team"])}</td>'
        f'<td style="padding:5px 8px;border-top:1px solid #eeede8">{html.escape(t["agent"])}</td>'
        f'<td style="padding:5px 8px;border-top:1px solid #eeede8;text-align:right">{t["hours_to_breach"]}</td>'
        f'<td style="padding:5px 8px;border-top:1px solid #eeede8;text-align:right;color:#d03b3b;font-weight:700">{pct(t["breach_risk"], 0)}</td>'
        f'<td style="padding:5px 8px;border-top:1px solid #eeede8;color:#52514e;font-size:12px">{html.escape("; ".join(t["why"]))}</td></tr>'
        for t in risk)
    th = 'style="text-align:left;padding:5px 8px;font-size:11px;color:#52514e;font-weight:600"'
    card = 'style="background:#fcfcfb;border:1px solid #e1e0d9;border-radius:8px;padding:14px 16px;margin:12px 0"'
    html_text = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>SLA Daily Report {day}</title></head>
<body style="margin:0;background:#f9f9f7;font-family:Segoe UI,Arial,sans-serif;color:#0b0b0b;font-size:14px">
<div style="max-width:860px;margin:0 auto;padding:20px">
  <div style="font-size:22px;font-weight:700">SLA Daily Report · {day}</div>
  <div style="color:#52514e;font-size:12px;margin-top:2px">Data as of {h['as_of']} · last {h['window']['days']} days
   ({h['window']['start']} to {h['window']['end']}) · status
   <b style="color:{sc}">{c['status']}</b> · {delta:+.1f} pts vs previous {h['baseline']['days']} days</div>
  <table role="presentation" style="width:100%;border-collapse:collapse;margin-top:12px"><tr>{tiles}</tr></table>
  <div {card}><div style="font-weight:700;margin-bottom:4px">Executive summary</div>
   <div style="font-size:11px;color:#52514e;margin-bottom:6px">written by {html.escape(author)}</div>{md_to_html(summary)}</div>
  <div {card}><div style="font-weight:700;margin-bottom:6px">Alerts · {h['counts']['critical']} critical ·
    {h['counts']['warning']} warning · {h['counts']['info']} info</div>
   <table style="width:100%;border-collapse:collapse">{alert_rows}</table></div>
  {"" if not rc else f'<div {card}><div style="font-weight:700;margin-bottom:6px">Root cause of breaches (last {h["window"]["days"]} days)</div><table role="presentation" style="border-collapse:collapse"><tr>{rc_html}</tr></table></div>'}
  {"" if not risk else f'<div {card}><div style="font-weight:700;margin-bottom:6px">Open tickets most likely to breach</div><table style="width:100%;border-collapse:collapse"><tr><th {th}>Ticket</th><th {th}>Pri</th><th {th}>Team</th><th {th}>Agent</th><th {th}>Hours left</th><th {th}>Risk</th><th {th}>Why</th></tr>{risk_rows}</table></div>'}
  <div style="color:#8a8983;font-size:11px;margin-top:10px">Breach-risk model: gradient boosting · ROC AUC {model_metrics['roc_auc']} ·
   PR AUC {model_metrics['pr_auc']} (base rate {pct(model_metrics['base_rate'])}) · tested on {model_metrics['test_period']}.
   Generated by the SLA Monitoring Agent on {datetime.now():%Y-%m-%d %H:%M}.</div>
</div></body></html>"""

    md_path = REPORTS_DIR / f"sla_report_{day}.md"
    html_path = REPORTS_DIR / f"sla_report_{day}.html"
    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    subject = (f"[SLA {c['status']}] {pct(c['res_sla'])} vs {pct(c['target'])} · "
               f"{h['counts']['critical']} critical alerts · {day}")
    return {"markdown": md_text, "html": html_text, "md_path": str(md_path), "html_path": str(html_path),
            "subject": subject, "summary": summary, "author": author}
