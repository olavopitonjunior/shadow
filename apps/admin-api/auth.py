import os

from fastapi import Header, HTTPException


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    """Valida token de admin se ADMIN_API_TOKEN estiver configurado."""
    token = os.getenv("ADMIN_API_TOKEN")
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    provided = authorization.replace("Bearer ", "", 1).strip()
    if provided != token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
