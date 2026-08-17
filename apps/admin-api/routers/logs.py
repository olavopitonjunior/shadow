"""Endpoints de logs."""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from auth import require_admin_token
from config import has_supabase, supabase_select

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
def get_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    level: Optional[str] = Query(None),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get aggregated logs (webhooks). Delegates to /webhooks."""
    if not has_supabase():
        return {"logs": [], "source": "no_storage"}

    params: dict[str, str] = {
        "order": "received_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    rows = supabase_select(
        "shadow_webhook_logs",
        "id,source,user_phone,contact_phone,direction,content_type,is_group,received_at",
        params,
    )
    return {"logs": rows}


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
    """Aggregate errors from alert_history, reminders, and cron_jobs."""
    if not has_supabase():
        return {"errors": [], "source": "no_storage"}

    errors: list[dict[str, Any]] = []

    # 1. Alert execution failures
    try:
        alert_rows = supabase_select(
            "shadow_alert_history",
            "id,alert_id,sent_at,error",
            {"error": "not.is.null", "order": "sent_at.desc", "limit": str(limit)},
        )
        for r in alert_rows:
            errors.append({
                "timestamp": r.get("sent_at"),
                "type": "alert_failure",
                "message": r.get("error", "Unknown alert error"),
                "source": f"alert:{r.get('alert_id', '?')}",
            })
    except Exception:
        pass

    # 2. Failed reminders
    try:
        reminder_rows = supabase_select(
            "shadow_reminders",
            "id,remind_at,last_error,attempts",
            {"failed": "eq.true", "order": "remind_at.desc", "limit": str(limit)},
        )
        for r in reminder_rows:
            errors.append({
                "timestamp": r.get("remind_at"),
                "type": "reminder_failure",
                "message": r.get("last_error", "Reminder delivery failed"),
                "source": f"reminder:{r.get('id', '?')}",
            })
    except Exception:
        pass

    # 3. Cron job failures
    try:
        cron_rows = supabase_select(
            "shadow_cron_jobs",
            "name,state_last_run,state_last_error",
            {"state_last_status": "eq.error", "order": "state_last_run.desc", "limit": str(limit)},
        )
        for r in cron_rows:
            errors.append({
                "timestamp": r.get("state_last_run"),
                "type": "cron_failure",
                "message": r.get("state_last_error", "Cron job failed"),
                "source": f"cron:{r.get('name', '?')}",
            })
    except Exception:
        pass

    errors.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return {"errors": errors[:limit]}
