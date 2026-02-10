"""Endpoints de usuarios."""
from typing import Any

from fastapi import APIRouter, Depends

from auth import require_admin_token
from config import has_supabase, supabase_select

router = APIRouter(tags=["users"])


@router.get("/users")
def users(_auth: None = Depends(require_admin_token)) -> dict[str, Any]:
    if not has_supabase():
        return {"users": [], "source": "no_storage"}

    rows = supabase_select(
        "shadow_users",
        "id,phone_number,name,created_at,updated_at",
        {"order": "created_at.desc", "limit": "100"},
    )
    return {"users": rows}
