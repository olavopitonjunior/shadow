"""Endpoints de configuracao e ambiente."""
import os
from typing import Any

from fastapi import APIRouter, Depends

from auth import require_admin_token

router = APIRouter(prefix="/config", tags=["config"])

# Variaveis de ambiente que o dashboard verifica (sem mostrar valores)
ENV_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "SHADOW_GATEWAY_URL",
    "SHADOW_GATEWAY_PORT",
    "SHADOW_AGENT_PORT",
    "OWNER_PHONE",
    "ADMIN_API_TOKEN",
]


@router.get("/environment")
def environment(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    """Retorna status das variaveis de ambiente (configurado/ausente, sem valores)."""
    status = {}
    for var in ENV_VARS:
        value = os.getenv(var)
        if value:
            # Mascarar valor
            if len(value) > 8:
                masked = value[:4] + "..." + value[-4:]
            else:
                masked = "****"
            status[var] = {"configured": True, "preview": masked}
        else:
            status[var] = {"configured": False}
    return {"variables": status}


@router.get("/providers")
def providers(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    """Status de API keys por provider."""
    return {
        "providers": {
            "anthropic": {
                "configured": bool(os.getenv("ANTHROPIC_API_KEY")),
                "models": ["claude-sonnet-4-20250514"],
            },
            "google": {
                "configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
                "models": ["gemini-2.5-flash-lite", "gemini-2.0-flash"],
            },
            "openai": {
                "configured": bool(os.getenv("OPENAI_API_KEY")),
                "models": ["text-embedding-3-small"],
            },
        }
    }
