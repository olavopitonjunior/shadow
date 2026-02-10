import os
from typing import Any

import httpx


# URLs dos servicos
AGENT_URL = os.getenv("SHADOW_AGENT_URL", "http://localhost:8090")
GATEWAY_URL = os.getenv("SHADOW_GATEWAY_URL", "http://localhost:18790")

# Supabase (opcional)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def has_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def supabase_count(table: str, filters: list[tuple[str, str, Any]] | None = None) -> int:
    """Conta registros em tabela do Supabase."""
    if not has_supabase():
        return 0
    params: dict[str, str] = {"select": "id"}
    for col, op, value in filters or []:
        params[col] = f"{op}.{value}"
    with httpx.Client(timeout=10) as client:
        res = client.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}",
            params=params,
            headers={**supabase_headers(), "Prefer": "count=exact"},
        )
        res.raise_for_status()
        content_range = res.headers.get("content-range") or ""
        if "/" in content_range:
            try:
                return int(content_range.split("/")[-1])
            except Exception:
                return 0
        return len(res.json() or [])


def supabase_select(table: str, select: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Seleciona registros de tabela do Supabase."""
    if not has_supabase():
        return []
    query = params.copy() if params else {}
    query["select"] = select
    with httpx.Client(timeout=10) as client:
        res = client.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}",
            params=query,
            headers=supabase_headers(),
        )
        res.raise_for_status()
        return res.json() or []


def get_supabase_config() -> dict[str, Any]:
    rows = supabase_select("shadow_config", "*", {"limit": "1"})
    return rows[0] if rows else {}
