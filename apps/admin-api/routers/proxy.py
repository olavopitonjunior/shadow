"""Proxy endpoints que redirecionam para Agent API e Gateway."""
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from auth import require_admin_token
from config import AGENT_URL, GATEWAY_URL

router = APIRouter(prefix="/proxy", tags=["proxy"])


async def _proxy_get(base_url: str, path: str) -> dict[str, Any]:
    """Faz GET request para servico externo e retorna JSON."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{base_url}{path}")
            res.raise_for_status()
            return res.json()
    except httpx.ConnectError:
        return {"error": "Service unavailable", "url": f"{base_url}{path}"}
    except Exception as exc:
        return {"error": str(exc), "url": f"{base_url}{path}"}


@router.get("/agent/status")
async def agent_status(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    return await _proxy_get(AGENT_URL, "/status")


@router.get("/agent/sessions")
async def agent_sessions(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    return await _proxy_get(AGENT_URL, "/sessions")


@router.get("/agent/sessions/{session_id}")
async def agent_session_detail(session_id: str, _auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    return await _proxy_get(AGENT_URL, f"/sessions/{session_id}")


@router.get("/agent/audit/summary")
async def agent_audit_summary(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    return await _proxy_get(AGENT_URL, "/audit/summary")


@router.get("/gateway/status")
async def gateway_status(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    return await _proxy_get(GATEWAY_URL, "/status")


@router.get("/gateway/groups")
async def gateway_groups(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    return await _proxy_get(GATEWAY_URL, "/groups")
