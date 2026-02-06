import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Carrega .env do diretório do agent (não depende de CWD)
_agent_dir = Path(__file__).parent
load_dotenv(_agent_dir / ".env")

# Debug: mostrar se GEMINI_API_KEY foi carregada
_gemini_key = os.getenv("GEMINI_API_KEY")
print(f"[config] GEMINI_API_KEY loaded: {bool(_gemini_key)}")


def resolve_db_path() -> str:
    default_path = Path(__file__).parent / "data" / "shadow.db"
    return os.getenv("SHADOW_DB_PATH", str(default_path))


@dataclass(frozen=True)
class AgentConfig:
    owner_e164: str | None
    gateway_send_url: str | None
    daily_summary_hour_utc: int
    access_mode: str  # "owner" or "open"
    gemini_api_key: str | None


def load_config() -> AgentConfig:
    owner = os.getenv("SHADOW_OWNER_E164")
    gateway_url = os.getenv("SHADOW_GATEWAY_SEND_URL")
    daily_hour = int(os.getenv("SHADOW_DAILY_SUMMARY_HOUR_UTC", "9"))
    access_mode = os.getenv("SHADOW_ACCESS_MODE", "owner")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return AgentConfig(
        owner_e164=owner,
        gateway_send_url=gateway_url,
        daily_summary_hour_utc=daily_hour,
        access_mode=access_mode,
        gemini_api_key=gemini_key,
    )