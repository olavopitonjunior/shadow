"""
Integrations Router - Connected services health and configuration.

Endpoints:
- GET /integrations — All connected services + status
- GET /integrations/{name}/health — Health check for specific service
- POST /integrations/{name}/reconnect — Reconnect a service
- GET /integrations/lancedb/stats — Vector DB statistics
"""

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter

_agent_path = str(Path(__file__).parent.parent.parent.parent / "shadow" / "agent")
if _agent_path not in sys.path:
    sys.path.insert(0, _agent_path)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _check_endpoint(url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Check if an HTTP endpoint is reachable."""
    try:
        start = time.time()
        resp = httpx.get(url, timeout=timeout)
        latency = int((time.time() - start) * 1000)
        return {"status": "connected", "latency_ms": latency, "http_status": resp.status_code}
    except Exception as e:
        return {"status": "disconnected", "error": str(e)[:100]}


@router.get("")
def list_integrations() -> dict[str, Any]:
    """Get all connected services and their status."""
    integrations = []

    # Gateway (Baileys)
    gateway_url = os.getenv("SHADOW_GATEWAY_SEND_URL", "")
    if gateway_url:
        base = gateway_url.rsplit("/", 1)[0] if "/" in gateway_url else gateway_url
        health = _check_endpoint(f"{base}/health") if base else {"status": "not_configured"}
        integrations.append({
            "name": "baileys",
            "type": "gateway",
            "url": base,
            **health,
        })

    # Z-API
    zapi_id = os.getenv("ZAPI_INSTANCE_ID")
    zapi_token = os.getenv("ZAPI_TOKEN")
    if zapi_id and zapi_token:
        integrations.append({
            "name": "zapi",
            "type": "gateway",
            "instance_id": zapi_id,
            "status": "configured",
        })
    else:
        integrations.append({
            "name": "zapi",
            "type": "gateway",
            "status": "not_configured",
        })

    # LLM Providers
    providers = [
        ("anthropic", "ANTHROPIC_API_KEY", "Claude"),
        ("google", "GEMINI_API_KEY", "Gemini"),
        ("openai", "OPENAI_API_KEY", "OpenAI"),
    ]
    for name, env_key, display in providers:
        has_key = bool(os.getenv(env_key))
        integrations.append({
            "name": name,
            "type": "llm_provider",
            "display_name": display,
            "status": "configured" if has_key else "not_configured",
        })

    # LanceDB (RAG)
    lance_path = Path(_agent_path) / "data" / "knowledge_db"
    integrations.append({
        "name": "lancedb",
        "type": "vector_db",
        "path": str(lance_path),
        "status": "active" if lance_path.exists() else "not_initialized",
    })

    # LangSmith
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    integrations.append({
        "name": "langsmith",
        "type": "observability",
        "status": "active" if tracing else "inactive",
        "project": os.getenv("LANGCHAIN_PROJECT", "default"),
    })

    # LangGraph
    integrations.append({
        "name": "langgraph",
        "type": "orchestration",
        "status": "active" if os.getenv("SHADOW_USE_LANGGRAPH", "").lower() in {"1", "true"} else "inactive",
    })

    return {"integrations": integrations}


@router.get("/{name}/health")
def check_integration_health(name: str) -> dict[str, Any]:
    """Health check for a specific integration."""
    if name == "baileys":
        url = os.getenv("SHADOW_GATEWAY_SEND_URL", "")
        if url:
            base = url.rsplit("/", 1)[0]
            return {"name": name, **_check_endpoint(f"{base}/health")}
        return {"name": name, "status": "not_configured"}

    if name == "agent":
        agent_url = os.getenv("SHADOW_AGENT_URL", "http://localhost:8090")
        return {"name": name, **_check_endpoint(f"{agent_url}/health")}

    if name == "zapi":
        zapi_id = os.getenv("ZAPI_INSTANCE_ID")
        zapi_token = os.getenv("ZAPI_TOKEN")
        if zapi_id and zapi_token:
            return {"name": name, **_check_endpoint(
                f"https://api.z-api.io/instances/{zapi_id}/token/{zapi_token}/status"
            )}
        return {"name": name, "status": "not_configured"}

    return {"name": name, "status": "unknown"}


@router.get("/lancedb/stats")
def get_lancedb_stats() -> dict[str, Any]:
    """Get LanceDB vector database statistics."""
    try:
        import lancedb
        db_path = str(Path(_agent_path) / "data" / "knowledge_db")
        db = lancedb.connect(db_path)
        tables = db.table_names()

        stats = {}
        for table_name in tables:
            table = db.open_table(table_name)
            stats[table_name] = {
                "row_count": table.count_rows(),
            }

        return {"path": db_path, "tables": stats, "table_count": len(tables)}
    except Exception as e:
        return {"error": str(e)[:200], "tables": {}}


@router.post("/{name}/reconnect")
def reconnect_integration(name: str) -> dict[str, Any]:
    """Attempt to reconnect a service."""
    # TODO: Implement reconnection logic per service
    return {"name": name, "status": "reconnect_requested"}
