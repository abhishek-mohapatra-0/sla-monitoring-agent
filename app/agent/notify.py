"""
Send the daily report: e-mail (any SMTP server, e.g. Gmail with an App Password)
and/or a chat webhook (Slack, Microsoft Teams, Discord, Google Chat).
Both are optional - configure them in app/.env.
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage


def send_email(s, rep) -> str:
    msg = EmailMessage()
    msg["Subject"] = rep["subject"]
    msg["From"] = s.smtp_user
    msg["To"] = s.email_to
    msg.set_content(rep["markdown"])
    msg.add_alternative(rep["html"], subtype="html")
    ctx = ssl.create_default_context()
    if int(s.smtp_port) == 465:
        with smtplib.SMTP_SSL(s.smtp_host, 465, context=ctx, timeout=30) as smtp:
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(s.smtp_host, int(s.smtp_port), timeout=30) as smtp:
            smtp.starttls(context=ctx)
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    return f"emailed to {s.email_to}"


def send_webhook(url, rep) -> str:
    text = f"*{rep['subject']}*\n\n{rep['summary']}"
    if "discord.com" in url:
        body = {"content": text[:1990]}
    elif "office.com" in url or "logic.azure.com" in url or "powerautomate" in url:
        body = {"text": text.replace("\n", "<br>")}              # Teams incoming webhook / workflow
    else:
        body = {"text": text}                                      # Slack, Google Chat, Mattermost
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return f"webhook {r.status}"


def notify(s, rep) -> dict:
    out = {}
    if s.email_enabled:
        try:
            out["email"] = send_email(s, rep)
        except Exception as e:
            out["email"] = f"failed: {type(e).__name__}: {e}"
    if s.webhook_url:
        try:
            out["webhook"] = send_webhook(s.webhook_url, rep)
        except Exception as e:
            out["webhook"] = f"failed: {type(e).__name__}: {e}"
    if not out:
        out["note"] = "nothing configured - set SMTP_* or WEBHOOK_URL in app/.env to send alerts"
    return out
