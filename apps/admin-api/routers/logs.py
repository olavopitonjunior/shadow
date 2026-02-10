"""Endpoints de logs."""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from auth import require_admin_token
from config import has_supabase, supabase_select

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/webhooks")
def webhook_logs(
    source: Optional[str] = Query(None, description="Filtrar por source"),
    direction: Optional[str] = Query(None, description="Filtrar por direction"),
    date_from: Optional[str] = Query(None, description="Data inicial (ISO)"),
    date_to: Optional[str] = Query(None, description="Data final (ISO)"),
    search: Optional[str] = Query(None, description="Busca em contact_phone"),
    limit: int = Query(100, ge=1, le=500),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    if not has_supabase():
        return {"logs": [], "source": "no_storage"}

    params: dict[str, str] = {
        "order": "received_at.desc",
        "limit": str(limit),
    }
    if source:
        params["source"] = f"eq.{source}"
    if direction:
        params["direction"] = f"eq.{direction}"
    if date_from:
        params["received_at"] = f"gte.{date_from}"
    if date_to:
        # Se ja tem filtro de data, compor com and
        if "received_at" in params:
            params["received_at"] = f"gte.{date_from}"
            params["and"] = f"(received_at.lte.{date_to})"
        else:
            params["received_at"] = f"lte.{date_to}"
    if search:
        params["contact_phone"] = f"like.%{search}%"

    rows = supabase_select(
        "shadow_webhook_logs",
        "id,source,user_phone,contact_phone,direction,content_type,is_group,received_at",
        params,
    )
    return {"logs": rows}


@router.get("/errors")
def error_logs(
    limit: int = Query(50, ge=1, le=200),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    # Por enquanto retorna webhook logs com erros (pode ser expandido)
    return {"errors": [], "note": "Error log collection not yet implemented"}
