"""Endpoints de uso de API e custos por provider."""
import os
import sys
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from auth import require_admin_token

router = APIRouter(tags=["usage"])


def _get_storage():
    """Tenta importar storage do agent para acesso ao SQLite."""
    try:
        agent_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "shadow", "agent")
        if agent_dir not in sys.path:
            sys.path.insert(0, agent_dir)
        from storage import Storage
        return Storage()
    except Exception:
        return None


@router.get("/stats/usage")
def usage_summary(
    days: int = Query(30, ge=1, le=365),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Resumo de uso agrupado por provider/modelo."""
    storage = _get_storage()
    if storage and hasattr(storage, "get_usage_summary"):
        return {"usage": storage.get_usage_summary(days)}
    return {"usage": [], "note": "Storage not available"}


@router.get("/stats/usage/history")
def usage_history(
    days: int = Query(30, ge=1, le=365),
    provider: Optional[str] = Query(None),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Uso diario ao longo do tempo."""
    storage = _get_storage()
    if storage and hasattr(storage, "get_usage_history"):
        return {"history": storage.get_usage_history(days, provider or "")}
    return {"history": [], "note": "Storage not available"}


@router.get("/stats/costs/breakdown")
def costs_breakdown(
    days: int = Query(30, ge=1, le=365),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Custos por provider com pricing aplicado."""
    storage = _get_storage()
    if not storage or not hasattr(storage, "get_usage_summary"):
        return {"providers": {}, "total_cost": 0.0}

    usage = storage.get_usage_summary(days)

    providers: dict[str, dict[str, Any]] = {}
    total_cost = 0.0

    for row in usage:
        provider = row["provider"]
        if provider not in providers:
            providers[provider] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "calls": 0,
                "avg_latency_ms": 0,
                "errors": 0,
                "models": {},
            }
        p = providers[provider]
        p["input_tokens"] += row.get("total_input", 0)
        p["output_tokens"] += row.get("total_output", 0)
        p["cost_usd"] += row.get("total_cost", 0.0)
        p["calls"] += row.get("call_count", 0)
        p["errors"] += row.get("error_count", 0)
        p["models"][row["model"]] = {
            "input_tokens": row.get("total_input", 0),
            "output_tokens": row.get("total_output", 0),
            "cost_usd": row.get("total_cost", 0.0),
            "calls": row.get("call_count", 0),
        }
        total_cost += row.get("total_cost", 0.0)

    # Calcular avg_latency para cada provider
    for provider_name in providers:
        matching = [r for r in usage if r["provider"] == provider_name]
        total_calls = sum(r.get("call_count", 0) for r in matching)
        if total_calls > 0:
            weighted_latency = sum(
                r.get("avg_latency", 0) * r.get("call_count", 0) for r in matching
            )
            providers[provider_name]["avg_latency_ms"] = round(weighted_latency / total_calls)

    return {
        "providers": providers,
        "total_cost": round(total_cost, 4),
        "days": days,
    }


@router.get("/config/pricing")
def get_pricing(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    """Config de precos por provider/modelo."""
    storage = _get_storage()
    if storage and hasattr(storage, "get_provider_pricing"):
        return {"pricing": storage.get_provider_pricing()}
    return {"pricing": []}


@router.put("/config/pricing")
def update_pricing(
    provider: str = Query(...),
    model: str = Query(...),
    input_price: float = Query(..., ge=0),
    output_price: float = Query(..., ge=0),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Atualizar preco de um provider/modelo."""
    storage = _get_storage()
    if storage and hasattr(storage, "update_provider_pricing"):
        storage.update_provider_pricing(provider, model, input_price, output_price)
        return {"status": "updated", "provider": provider, "model": model}
    return {"error": "Storage not available"}
