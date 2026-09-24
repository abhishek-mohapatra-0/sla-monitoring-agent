"""
Tiny OpenAI-compatible client with a tool-calling loop (standard library only).

Works with Groq, Google Gemini, OpenRouter, Ollama and OpenAI because they all
accept POST {base_url}/chat/completions with "tools".
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

MAX_TOOL_CHARS = 12000


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: int = 90):
        self.base_url, self.model, self.api_key, self.timeout = base_url, model, api_key, timeout

    def complete(self, messages: list[dict], tools: list[dict] | None = None, temperature=0.2) -> dict:
        body = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        data = json.dumps(body).encode()
        for attempt in range(4):
            req = urllib.request.Request(self.base_url + "/chat/completions", data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "sla-monitoring-agent")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                txt = e.read().decode(errors="replace")[:600]
                if e.code in (429, 500, 502, 503) and attempt < 3:
                    time.sleep(2 * (attempt + 1) + (4 if e.code == 429 else 0))
                    continue
                raise LLMError(f"HTTP {e.code}: {txt}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 2:
                    time.sleep(2)
                    continue
                raise LLMError(f"Cannot reach {self.base_url}: {getattr(e, 'reason', e)}") from None
        raise LLMError("No response")

    def run_tools(self, messages: list[dict], tools: list[dict], execute, max_steps: int = 6):
        """Loop: model -> tool calls -> results -> model ... until it answers in text.
        Returns (answer_text, trace) where trace lists every tool call."""
        trace = []
        for step in range(max_steps):
            try:
                resp = self.complete(messages, tools)
            except LLMError as e:
                # some models occasionally emit a malformed tool call - retry once, then give up
                if "tool_use_failed" in str(e) and step == 0:
                    continue
                raise
            msg = resp["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            if not calls:
                return (msg.get("content") or "").strip(), trace
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": [{"id": c["id"], "type": "function",
                                             "function": {"name": c["function"]["name"],
                                                          "arguments": c["function"].get("arguments") or "{}"}}
                                            for c in calls]})
            for c in calls:
                name = c["function"]["name"]
                raw = c["function"].get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                result = execute(name, args)
                trace.append({"tool": name, "args": args, "ok": "error" not in result})
                content = json.dumps(result, default=str)
                if len(content) > MAX_TOOL_CHARS:
                    content = content[:MAX_TOOL_CHARS] + '..."(truncated)"'
                messages.append({"role": "tool", "tool_call_id": c["id"], "name": name, "content": content})
        # out of steps: ask for a final answer without tools
        messages.append({"role": "user", "content": "Answer now using the tool results above."})
        resp = self.complete(messages)
        return (resp["choices"][0]["message"].get("content") or "").strip(), trace
