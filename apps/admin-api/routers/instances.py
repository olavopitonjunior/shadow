"""Instance management endpoints."""
import os
import sys
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import require_admin_token
from config import GATEWAY_URL, AGENT_URL

router = APIRouter(prefix="/instances", tags=["instances"])


class CreateInstanceBody(BaseModel):
    name: str


def _get_storage():
    """Import agent storage for instance data."""
    try:
        agent_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "shadow", "agent")
        if agent_dir not in sys.path:
            sys.path.insert(0, agent_dir)
        # Temporarily swap out admin-api's 'config' module to avoid collision
        # with shadow/agent/config.py (which has resolve_db_path).
        _orig_config = sys.modules.pop("config", None)
        try:
            from storage import Storage
            return Storage()
        finally:
            if _orig_config is not None:
                sys.modules["config"] = _orig_config
    except Exception:
        return None


def _gateway_request(method: str, path: str, json_data: dict | None = None, timeout: int = 10) -> dict:
    """Make request to gateway."""
    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                res = client.get(f"{GATEWAY_URL}{path}")
            elif method == "POST":
                res = client.post(f"{GATEWAY_URL}{path}", json=json_data or {})
            elif method == "DELETE":
                res = client.delete(f"{GATEWAY_URL}{path}")
            else:
                return {"error": f"Unsupported method: {method}"}
            return res.json()
    except httpx.ConnectError:
        return {"error": "Gateway unavailable"}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("")
def create_instance(
    body: CreateInstanceBody,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Create a new instance and initiate gateway connection."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance_id = str(uuid4())[:8]
    gateway_user_id = instance_id

    # Save to storage
    storage.create_instance(instance_id, body.name, gateway_user_id)

    # Connect via gateway
    gw_result = _gateway_request("POST", f"/sessions/{gateway_user_id}/connect")

    # Update status based on gateway response
    status = gw_result.get("status", "disconnected")
    storage.update_instance(instance_id, status=status)

    instance = storage.get_instance(instance_id)
    instance["qr"] = gw_result.get("qr")
    return instance


@router.get("")
def list_instances(
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """List all instances with live status from gateway."""
    storage = _get_storage()
    if not storage:
        return {"instances": []}

    instances = storage.list_instances()

    # Enrich with live gateway status
    gw_sessions = _gateway_request("GET", "/sessions")
    session_map = {}
    for s in gw_sessions.get("sessions", []):
        session_map[s["userId"]] = s

    for inst in instances:
        gw = session_map.get(inst["gateway_user_id"], {})
        if gw:
            inst["live_status"] = gw.get("status", inst["status"])
            inst["live_phone"] = gw.get("phone")
        else:
            inst["live_status"] = inst["status"]
            inst["live_phone"] = inst.get("phone")

    return {"instances": instances}


@router.get("/{instance_id}")
def get_instance(
    instance_id: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get instance details with live status."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    # Live status from gateway
    gw = _gateway_request("GET", f"/sessions/{instance['gateway_user_id']}/status")
    instance["live_status"] = gw.get("status", instance["status"])
    instance["live_phone"] = gw.get("phone")

    return instance


@router.delete("/{instance_id}")
def delete_instance(
    instance_id: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Disconnect and remove an instance."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    # Disconnect from gateway
    _gateway_request("DELETE", f"/sessions/{instance['gateway_user_id']}")

    # Remove from storage
    storage.delete_instance(instance_id)
    return {"status": "deleted", "id": instance_id}


@router.post("/{instance_id}/connect")
def connect_instance(
    instance_id: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Reconnect an existing instance."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    result = _gateway_request("POST", f"/sessions/{instance['gateway_user_id']}/connect")
    status = result.get("status", "disconnected")
    storage.update_instance(instance_id, status=status)

    return {"id": instance_id, "status": status, "qr": result.get("qr")}


@router.post("/{instance_id}/disconnect")
def disconnect_instance(
    instance_id: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Disconnect without removing the instance."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    _gateway_request("DELETE", f"/sessions/{instance['gateway_user_id']}")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    storage.update_instance(instance_id, status="disconnected", disconnected_at=now)

    return {"id": instance_id, "status": "disconnected"}


@router.get("/{instance_id}/qr")
def get_instance_qr(
    instance_id: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get QR code for scanning."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    result = _gateway_request("GET", f"/sessions/{instance['gateway_user_id']}/qr")
    return {
        "qr": result.get("qr"),
        "status": result.get("status", "disconnected"),
        "qr_updated_at": result.get("qr_updated_at"),
    }


@router.get("/{instance_id}/status")
def get_instance_status(
    instance_id: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get live connection status."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    result = _gateway_request("GET", f"/sessions/{instance['gateway_user_id']}/status")

    status = result.get("status", "disconnected")
    phone = result.get("phone")

    # Update stored status and phone if changed
    updates = {"status": status}
    if phone and phone != instance.get("phone"):
        updates["phone"] = phone
        updates["owner_e164"] = phone
    if status == "connected" and not instance.get("connected_at"):
        from datetime import datetime, timezone
        updates["connected_at"] = datetime.now(timezone.utc).isoformat()
    storage.update_instance(instance_id, **updates)

    return {
        "status": status,
        "phone": phone,
        "qr": result.get("qr"),
        "qr_updated_at": result.get("qr_updated_at"),
    }


@router.get("/{instance_id}/stats")
def get_instance_stats(
    instance_id: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get instance metrics summary."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    # Get session stats from agent
    stats = {"messages": 0, "sessions": 0, "input_tokens": 0, "output_tokens": 0}
    try:
        with httpx.Client(timeout=10) as client:
            res = client.get(f"{AGENT_URL}/sessions")
            sessions = res.json() if res.status_code == 200 else []
            if isinstance(sessions, dict):
                sessions = sessions.get("sessions", [])
            for s in sessions:
                participant = s.get("participant_phone", "")
                if instance.get("owner_e164") and participant and instance["owner_e164"] == participant:
                    stats["sessions"] += 1
                    stats["messages"] += s.get("message_count", 0)
                    stats["input_tokens"] += s.get("input_tokens", 0)
                    stats["output_tokens"] += s.get("output_tokens", 0)
    except Exception:
        pass

    # Get cost from API usage
    if hasattr(storage, "get_usage_summary"):
        try:
            usage = storage.get_usage_summary(30)
            stats["total_cost"] = sum(r.get("total_cost", 0) for r in usage)
        except Exception:
            stats["total_cost"] = 0
    else:
        stats["total_cost"] = 0

    return stats


@router.get("/{instance_id}/conversations")
def get_instance_conversations(
    instance_id: str,
    limit: int = Query(50, ge=1, le=200),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get conversations for this instance."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    # Get sessions from agent
    try:
        with httpx.Client(timeout=10) as client:
            res = client.get(f"{AGENT_URL}/sessions")
            sessions = res.json() if res.status_code == 200 else []
            if isinstance(sessions, dict):
                sessions = sessions.get("sessions", [])
    except Exception:
        sessions = []

    # Filter by instance owner phone
    owner = instance.get("owner_e164")
    if owner:
        sessions = [
            s for s in sessions
            if s.get("participant_phone") == owner
        ]
    return {"conversations": sessions[:limit]}


@router.get("/{instance_id}/costs")
def get_instance_costs(
    instance_id: str,
    days: int = Query(30, ge=1, le=365),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get costs breakdown for this instance."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    # Return costs filtered by instance gateway_user_id when available
    if hasattr(storage, "get_usage_summary"):
        usage = storage.get_usage_summary(days)
        providers = {}
        total_cost = 0.0
        for row in usage:
            provider = row["provider"]
            if provider not in providers:
                providers[provider] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
            p = providers[provider]
            p["input_tokens"] += row.get("total_input", 0)
            p["output_tokens"] += row.get("total_output", 0)
            p["cost_usd"] += row.get("total_cost", 0.0)
            p["calls"] += row.get("call_count", 0)
            total_cost += row.get("total_cost", 0.0)
        return {"providers": providers, "total_cost": round(total_cost, 4), "days": days}
    return {"providers": {}, "total_cost": 0.0, "days": days}


@router.get("/{instance_id}/logs")
def get_instance_logs(
    instance_id: str,
    limit: int = Query(100, ge=1, le=500),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get logs for this instance."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    # For now, return API usage logs as application logs
    if hasattr(storage, "get_usage_history"):
        history = storage.get_usage_history(30, "")
        return {"logs": history[:limit]}
    return {"logs": []}
