"""
Settings, read from app/.env (copy .env.example -> .env and fill in what you need).

No key at all?  The agent still works in OFFLINE mode (rule-based answers).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = APP_DIR.parent
REPORTS_DIR = ROOT_DIR / "reports"

# Free / free-tier providers that speak the OpenAI "chat completions + tools" format
PROVIDERS = {
    "groq":       {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile",
                   "key_url": "https://console.groq.com/keys"},
    "gemini":     {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash",
                   "key_url": "https://aistudio.google.com/apikey"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "meta-llama/llama-3.3-70b-instruct:free",
                   "key_url": "https://openrouter.ai/keys"},
    "ollama":     {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b", "key_url": None},
    "openai":     {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
                   "key_url": "https://platform.openai.com/api-keys"},
}


def load_env(*files: Path) -> None:
    """Minimal .env reader (KEY=value lines, # comments). Real env vars win."""
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


@dataclass
class Settings:
    provider: str = "none"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_to: str = ""
    webhook_url: str = ""
    report_window_days: int = 30

    @property
    def llm_enabled(self) -> bool:
        return self.provider in PROVIDERS and (bool(self.api_key) or self.provider == "ollama")

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.email_to)

    @property
    def label(self) -> str:
        return f"{self.provider} · {self.model}" if self.llm_enabled else "offline (rule-based)"


def get_settings() -> Settings:
    load_env(APP_DIR / ".env", ROOT_DIR / ".env")
    e = os.environ.get
    provider = (e("LLM_PROVIDER") or "none").strip().lower()
    preset = PROVIDERS.get(provider, {})
    return Settings(
        provider=provider,
        api_key=(e("LLM_API_KEY") or "").strip(),
        model=(e("LLM_MODEL") or preset.get("model", "")).strip(),
        base_url=(e("LLM_BASE_URL") or preset.get("base_url", "")).strip().rstrip("/"),
        smtp_host=e("SMTP_HOST", ""), smtp_port=int(e("SMTP_PORT") or 587),
        smtp_user=e("SMTP_USER", ""), smtp_password=e("SMTP_PASSWORD", ""),
        email_to=e("ALERT_EMAIL_TO", ""),
        webhook_url=e("WEBHOOK_URL", ""),
        report_window_days=int(e("REPORT_WINDOW_DAYS") or 30),
    )
