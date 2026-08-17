"""Channel management endpoints for admin dashboard.

Manage channel users, messages, templates, and configuration.
"""

import os
import sys
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import require_admin_token

router = APIRouter(prefix="/channel", tags=["channel"])


def _get_storage():
    """Import agent storage for channel data."""
    try:
        agent_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "..", "shadow", "agent",
        )
        if agent_dir not in sys.path:
            sys.path.insert(0, agent_dir)
        _orig_config = sys.modules.pop("config", None)
        try:
            from storage import Storage
            return Storage()
        finally:
            if _orig_config is not None:
                sys.modules["config"] = _orig_config
    except Exception:
        return None


# ── Channel Users ─────────────────────────────────────────────────


@router.get("/users")
def list_channel_users(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """List channel users with optional status filter."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    users = storage.list_channel_users(status=status, limit=limit)
    return {"users": users, "total": len(users)}


@router.get("/users/{phone}")
def get_channel_user(
    phone: str,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get channel user details by phone."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    user = storage.get_channel_user_by_phone(phone)
    if not user:
        raise HTTPException(404, "User not found")
    return user


class UpdateUserBody(BaseModel):
    status: str | None = None
    display_name: str | None = None
    user_type: str | None = None


@router.patch("/users/{phone}")
def update_channel_user(
    phone: str,
    body: UpdateUserBody,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Update channel user (block/unblock, change type, etc.)."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    result = storage.update_channel_user(phone, **updates)
    if not result:
        raise HTTPException(404, "User not found")
    return result


# ── Channel Messages ──────────────────────────────────────────────


@router.get("/messages")
def list_channel_messages(
    phone: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """List channel messages with pagination."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    messages = storage.list_channel_messages(
        user_phone=phone, limit=limit, offset=offset
    )
    return {"messages": messages, "total": len(messages)}


# ── Channel Templates ─────────────────────────────────────────────


@router.get("/templates")
def list_channel_templates(
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """List all channel templates."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    templates = storage.list_channel_templates()
    return {"templates": templates, "total": len(templates)}


class CreateTemplateBody(BaseModel):
    template_name: str
    body_text: str
    category: str = "UTILITY"
    language: str = "pt_BR"


@router.post("/templates")
def create_channel_template(
    body: CreateTemplateBody,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Create a new channel template."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    result = storage.create_channel_template(
        template_name=body.template_name,
        body_text=body.body_text,
        category=body.category,
        language=body.language,
    )
    return result


class UpdateTemplateStatusBody(BaseModel):
    status: str  # draft, submitted, approved, rejected


@router.patch("/templates/{template_name}")
def update_channel_template(
    template_name: str,
    body: UpdateTemplateStatusBody,
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Update template status."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    result = storage.update_channel_template_status(template_name, body.status)
    if not result:
        raise HTTPException(404, "Template not found")
    return result


# ── Channel Stats ─────────────────────────────────────────────────


@router.get("/stats")
def channel_stats(
    _auth: None = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get channel statistics."""
    storage = _get_storage()
    if not storage:
        raise HTTPException(500, "Storage unavailable")

    users = storage.list_channel_users()
    messages = storage.list_channel_messages(limit=1000)

    active_users = sum(1 for u in users if u.get("status") == "active")
    onboarding_users = sum(1 for u in users if u.get("status") == "onboarding")
    blocked_users = sum(1 for u in users if u.get("status") == "blocked")
    baileys_linked = sum(1 for u in users if u.get("user_type") == "baileys_linked")

    inbound = sum(1 for m in messages if m.get("direction") == "inbound")
    outbound = sum(1 for m in messages if m.get("direction") == "outbound")

    return {
        "users": {
            "total": len(users),
            "active": active_users,
            "onboarding": onboarding_users,
            "blocked": blocked_users,
            "baileys_linked": baileys_linked,
        },
        "messages": {
            "total": len(messages),
            "inbound": inbound,
            "outbound": outbound,
        },
    }
