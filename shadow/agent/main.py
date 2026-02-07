"""
Shadow Agent MVP - API Principal

Endpoints:
- POST /process - Processa mensagem do WhatsApp
- GET /health - Health check
- GET /summary - Resumo de tarefas/compromissos
- GET /today - Agenda do dia
- GET /contacts - Lista de contatos recentes
- GET /contacts/{phone}/timeline - Timeline de um contato
- GET /audit - Auditoria de segurança
- GET /sessions - Lista sessões ativas
- GET /sessions/{id} - Detalhes de uma sessão
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import load_config
from message_handler import handle_message
from storage import Storage
from sessions import SessionStore, get_session_store
from security import (
    SecurityAudit,
    RateLimiter,
    AccessPolicy,
    get_rate_limiter,
    get_access_policy,
)
from scheduler import ShadowScheduler

app = FastAPI(
    title="Shadow Agent MVP",
    description="Agente secretário pessoal via WhatsApp",
    version="0.2.0",
)

# Inicialização dos componentes
config = load_config()
storage = Storage()
session_store = get_session_store()
rate_limiter = get_rate_limiter()
access_policy = get_access_policy()

# Scheduler para alertas e lembretes
scheduler: ShadowScheduler | None = None


@app.on_event("startup")
async def startup_event():
    """Inicia componentes assíncronos."""
    global scheduler
    scheduler = ShadowScheduler()
    await scheduler.start()
    print("[main] Scheduler started")


@app.on_event("shutdown")
async def shutdown_event():
    """Para componentes assíncronos."""
    global scheduler
    if scheduler:
        await scheduler.stop()
        print("[main] Scheduler stopped")


class ProcessRequest(BaseModel):
    message_id: str | None = None
    chat_id: str | None = None
    chat_type: str | None = None
    sender_e164: str | None = None
    sender_jid: str | None = None  # Phase 7: Fallback when E.164 resolution fails
    sender_name: str | None = None
    owner_e164: str | None = None
    body: str | None = None
    timestamp: int | None = None
    is_owner: bool | None = None
    triggered: bool | None = None
    should_reply: bool | None = None
    monitor_only: bool | None = None  # Phase 7: Monitored messages (no reply)
    metadata: dict[str, Any] | None = None

    # Aliases para compatibilidade
    user_phone: str | None = None
    contact_phone: str | None = None
    content: str | None = None
    content_type: str | None = "text"

    # Mídia (para futuro)
    media_url: str | None = None
    media_mime_type: str | None = None
    media_type: str | None = None  # Phase 7B: Audio transcription


def require_token(authorization: str | None = Header(default=None)) -> None:
    """Verifica token de autenticação Bearer."""
    token = os.getenv("SHADOW_AGENT_TOKEN")
    if not token:
        return  # Token não configurado, acesso livre
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    provided = authorization.replace("Bearer ", "", 1).strip()
    if provided != token:
        raise HTTPException(status_code=401, detail="Invalid token")


def check_rate_limit(request: Request) -> None:
    """Verifica rate limit baseado no IP ou telefone."""
    # Usa IP como chave de rate limit
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        remaining = rate_limiter.reset_time(client_ip)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {int(remaining or 0)} seconds.",
        )


# === Health & Status ===

@app.get("/health")
def health() -> dict[str, Any]:
    """Health check do serviço."""
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "0.2.0",
    }


@app.get("/status")
def status(_auth: None = Depends(require_token)) -> dict[str, Any]:
    """Status completo do serviço."""
    session_stats = session_store.stats()
    scheduler_status = scheduler.status() if scheduler else {"running": False}
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "0.2.0",
        "components": {
            "storage": "ok",
            "sessions": "ok",
            "rate_limiter": "ok",
            "scheduler": "ok" if scheduler_status.get("running") else "stopped",
        },
        "sessions": session_stats,
        "scheduler": scheduler_status,
        "rate_limiter": {
            "max_requests": rate_limiter.max_requests,
            "window_seconds": rate_limiter.window_seconds,
        },
    }


# === Core Message Processing ===

@app.post("/process")
def process_message(
    payload: ProcessRequest,
    request: Request,
    _auth: None = Depends(require_token),
) -> dict[str, Any]:
    """
    Processa mensagem recebida do WhatsApp.

    Aplica:
    - Rate limiting
    - Verificação de acesso (owner/allowlist)
    - Gerenciamento de sessão
    """
    # Rate limit check
    check_rate_limit(request)

    try:
        data = payload.dict()

        # Verifica acesso se não for owner
        sender = data.get("sender_e164") or data.get("contact_phone")
        is_owner = data.get("is_owner")

        if not is_owner and sender:
            if not access_policy.is_allowed(sender):
                return {
                    "reply": None,
                    "intent": "blocked",
                    "actions": [],
                    "reason": "access_denied",
                }

        # Processa mensagem com sessão
        result = handle_message(data, storage, session_store)
        return result

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# === Tasks & Appointments ===

@app.get("/summary")
def summary(_auth: None = Depends(require_token)) -> dict[str, Any]:
    """Resumo de tarefas e compromissos."""
    tasks = storage.list_tasks()
    appointments = storage.list_appointments()
    return {
        "tasks_pending": len(tasks),
        "appointments_upcoming": len(appointments),
        "tasks": [{"id": t.id, "title": t.title, "due_at": t.due_at} for t in tasks[:10]],
        "appointments": [
            {"id": a.id, "title": a.title, "scheduled_at": a.scheduled_at}
            for a in appointments[:10]
        ],
    }


@app.get("/today")
def today(_auth: None = Depends(require_token)) -> dict[str, Any]:
    """Agenda do dia atual."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=1)
    appointments = [
        a for a in storage.list_appointments(50)
        if a.scheduled_at and a.scheduled_at <= end.isoformat()
    ]
    tasks = storage.list_tasks(50)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "appointments_today": [
            {"title": a.title, "scheduled_at": a.scheduled_at}
            for a in appointments
        ],
        "tasks_pending": [
            {"title": t.title, "due_at": t.due_at}
            for t in tasks
        ],
    }


# === Contacts ===

@app.get("/contacts")
def list_contacts(
    limit: int = 20,
    _auth: None = Depends(require_token),
) -> dict[str, Any]:
    """Lista contatos recentes."""
    contacts = storage.list_recent_contacts(limit)
    return {"contacts": contacts, "total": len(contacts)}


@app.get("/contacts/{phone}/timeline")
def contact_timeline(
    phone: str,
    limit: int = 20,
    _auth: None = Depends(require_token),
) -> dict[str, Any]:
    """Timeline de mensagens de um contato."""
    timeline = storage.list_contact_timeline(phone, limit)
    return {
        "phone": phone,
        "messages": timeline,
        "total": len(timeline),
    }


# === Sessions ===

@app.get("/sessions")
def list_sessions(
    limit: int = 50,
    _auth: None = Depends(require_token),
) -> dict[str, Any]:
    """Lista sessões ativas."""
    sessions = session_store.list_active(limit)
    return {
        "sessions": [
            {
                "id": s.id,
                "chat_id": s.chat_id,
                "participant_phone": s.participant_phone,
                "kind": s.kind,
                "status": s.status,
                "message_count": s.message_count,
                "last_activity_at": s.last_activity_at,
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@app.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    _auth: None = Depends(require_token),
) -> dict[str, Any]:
    """Detalhes de uma sessão específica."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    context = session_store.get_context(session_id, limit=20)
    return {
        "session": session.to_dict(),
        "context": [m.to_dict() for m in context],
    }


@app.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    _auth: None = Depends(require_token),
) -> dict[str, Any]:
    """Remove uma sessão."""
    success = session_store.delete(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True, "session_id": session_id}


@app.post("/sessions/{session_id}/clear")
def clear_session_context(
    session_id: str,
    _auth: None = Depends(require_token),
) -> dict[str, Any]:
    """Limpa contexto de uma sessão."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_store.clear_context(session_id)
    return {"cleared": True, "session_id": session_id}


# === Security ===

@app.get("/audit")
def security_audit(_auth: None = Depends(require_token)) -> dict[str, Any]:
    """
    Executa auditoria de segurança.

    Verifica:
    - Secrets expostos em arquivos
    - Variáveis de ambiente
    - Permissões de arquivos
    - Configuração do banco de dados
    - Segurança da API
    """
    audit = SecurityAudit()
    report = audit.run_full_audit()
    return report.to_dict()


@app.get("/audit/summary")
def security_summary(_auth: None = Depends(require_token)) -> dict[str, Any]:
    """Resumo rápido da auditoria de segurança."""
    audit = SecurityAudit()
    report = audit.run_full_audit()
    return {
        "status": "ok" if report.summary.critical == 0 else "warning",
        "critical": report.summary.critical,
        "warnings": report.summary.warn,
        "info": report.summary.info,
        "total_findings": len(report.findings),
    }


# === Rate Limit Info ===

@app.get("/rate-limit")
def rate_limit_info(request: Request) -> dict[str, Any]:
    """Informações de rate limit para o cliente atual."""
    client_ip = request.client.host if request.client else "unknown"
    return {
        "client": client_ip,
        "remaining": rate_limiter.remaining(client_ip),
        "max_requests": rate_limiter.max_requests,
        "window_seconds": rate_limiter.window_seconds,
        "reset_in_seconds": rate_limiter.reset_time(client_ip),
    }


# === Error Handlers ===

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )


# === Startup ===

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SHADOW_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("SHADOW_AGENT_PORT", "8090"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
