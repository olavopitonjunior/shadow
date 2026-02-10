"""Endpoints de visao geral e tabelas."""
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from auth import require_admin_token
from config import (
    AGENT_URL,
    GATEWAY_URL,
    has_supabase,
    supabase_count,
    supabase_select,
)

router = APIRouter(tags=["overview"])


@router.get("/stats/overview")
def overview(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    since_24h = (now - timedelta(hours=24)).isoformat()

    if has_supabase():
        return {
            "users_total": supabase_count("shadow_users"),
            "users_active_24h": supabase_count("shadow_sessions", [("last_activity_at", "gte", since_24h)]),
            "messages_total": supabase_count("shadow_messages"),
            "messages_24h": supabase_count("shadow_messages", [("timestamp", "gte", since_24h)]),
            "tasks_pending": supabase_count("shadow_tasks", [("status", "eq", "pending")]),
            "appointments_upcoming": supabase_count("shadow_appointments", [("scheduled_at", "gte", now.isoformat())]),
            "timestamp": now.isoformat(),
        }

    # Fallback: tenta buscar do Agent API
    try:
        with httpx.Client(timeout=10) as client:
            status = client.get(f"{AGENT_URL}/status").json()
            sessions = status.get("sessions", {})
            return {
                "users_total": sessions.get("total_sessions", 0),
                "users_active_24h": sessions.get("active_sessions", 0),
                "messages_total": sessions.get("total_messages", 0),
                "messages_24h": 0,
                "tasks_pending": 0,
                "appointments_upcoming": 0,
                "timestamp": now.isoformat(),
                "source": "agent_api",
            }
    except Exception:
        return {
            "users_total": 0, "users_active_24h": 0, "messages_total": 0,
            "messages_24h": 0, "tasks_pending": 0, "appointments_upcoming": 0,
            "timestamp": now.isoformat(), "source": "unavailable",
        }


@router.get("/stats/integrations")
def integrations(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    baileys = bool(os.getenv("SHADOW_GATEWAY_URL") or os.getenv("GATEWAY_URL"))

    return {
        "baileys": {"enabled": baileys},
    }


@router.get("/stats/whatsapp")
def whatsapp_status(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    connections: list[dict[str, Any]] = []

    # Baileys gateway
    try:
        with httpx.Client(timeout=5) as client:
            res = client.get(f"{GATEWAY_URL}/status")
            data = res.json()
            connections.append({
                "provider": "baileys",
                "instance_id": data.get("phone", "local"),
                "status": "connected" if data.get("status") == "connected" else "disconnected",
                "details": data.get("status"),
                "checked_at": now,
            })
    except Exception as exc:
        connections.append({
            "provider": "baileys",
            "instance_id": "local",
            "status": "error",
            "details": str(exc),
            "checked_at": now,
        })

    return {"connections": connections}


@router.get("/stats/tables")
def tables(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    table_names = [
        "shadow_users", "shadow_contacts", "shadow_conversations", "shadow_messages",
        "shadow_tasks", "shadow_appointments", "shadow_interactions", "shadow_reminders",
        "shadow_sessions", "shadow_webhook_logs", "shadow_feedback",
        "shadow_learned_patterns", "shadow_suggestions", "shadow_scheduled_alerts",
    ]
    if has_supabase():
        return {"tables": {name: supabase_count(name) for name in table_names}}
    return {"tables": {name: 0 for name in table_names}, "source": "no_storage"}


@router.get("/stats/costs")
def costs(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    if has_supabase():
        rows = supabase_select("shadow_sessions", "input_tokens,output_tokens")
        input_tokens = sum(int(r.get("input_tokens") or 0) for r in rows)
        output_tokens = sum(int(r.get("output_tokens") or 0) for r in rows)
    else:
        # Buscar do Agent API
        try:
            with httpx.Client(timeout=10) as client:
                status = client.get(f"{AGENT_URL}/status").json()
                sessions = status.get("sessions", {})
                input_tokens = sessions.get("total_input_tokens", 0)
                output_tokens = sessions.get("total_output_tokens", 0)
        except Exception:
            input_tokens = 0
            output_tokens = 0

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "note": "Cost estimation uses stored token counters. Configure provider pricing to refine.",
    }
