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
    # Channel adapter
    channel_enabled: bool = False
    channel_adapter: str = "none"  # "evolution" | "meta_cloud" | "none"
    # Evolution API
    evolution_api_url: str | None = None
    evolution_api_key: str | None = None
    evolution_instance: str | None = None
    # Meta Cloud API
    meta_whatsapp_token: str | None = None
    meta_phone_number_id: str | None = None
    meta_waba_id: str | None = None
    meta_verify_token: str | None = None
    meta_app_secret: str | None = None
    # Z-API
    zapi_instance_id: str | None = None
    zapi_token: str | None = None


def load_config() -> AgentConfig:
    owner = os.getenv("SHADOW_OWNER_E164")
    gateway_url = os.getenv("SHADOW_GATEWAY_SEND_URL")
    daily_hour = int(os.getenv("SHADOW_DAILY_SUMMARY_HOUR_UTC", "9"))
    access_mode = os.getenv("SHADOW_ACCESS_MODE", "owner")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    # Channel adapter config
    channel_adapter = os.getenv("SHADOW_CHANNEL_ADAPTER", "none").lower()
    channel_enabled = channel_adapter != "none" and os.getenv("SHADOW_CHANNEL_ENABLED", "false").lower() in {"1", "true", "yes"}

    return AgentConfig(
        owner_e164=owner,
        gateway_send_url=gateway_url,
        daily_summary_hour_utc=daily_hour,
        access_mode=access_mode,
        gemini_api_key=gemini_key,
        channel_enabled=channel_enabled,
        channel_adapter=channel_adapter,
        evolution_api_url=os.getenv("EVOLUTION_API_URL"),
        evolution_api_key=os.getenv("EVOLUTION_API_KEY"),
        evolution_instance=os.getenv("EVOLUTION_INSTANCE", "shadow"),
        meta_whatsapp_token=os.getenv("META_WHATSAPP_TOKEN"),
        meta_phone_number_id=os.getenv("META_PHONE_NUMBER_ID"),
        meta_waba_id=os.getenv("META_WABA_ID"),
        meta_verify_token=os.getenv("META_VERIFY_TOKEN", "shadow_verify"),
        meta_app_secret=os.getenv("META_APP_SECRET"),
        zapi_instance_id=os.getenv("ZAPI_INSTANCE_ID"),
        zapi_token=os.getenv("ZAPI_TOKEN"),
    )