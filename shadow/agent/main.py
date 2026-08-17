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
from bus import get_message_bus, OutboundMessage
from heartbeat import HeartbeatService
from channels import get_adapter, WebhookHandler, ChannelIncoming

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
heartbeat: HeartbeatService | None = None

# Channel adapter (Evolution API / Meta Cloud API)
channel_adapter = None
webhook_handler: WebhookHandler | None = None

if config.channel_enabled and config.channel_adapter != "none":
    try:
        adapter_kwargs = {}
        if config.channel_adapter == "evolution":
            adapter_kwargs = {
                "api_url": config.evolution_api_url or "",
                "api_key": config.evolution_api_key or "",
                "instance": config.evolution_instance or "shadow",
            }
        elif config.channel_adapter == "meta_cloud":
            adapter_kwargs = {
                "access_token": config.meta_whatsapp_token or "",
                "phone_number_id": config.meta_phone_number_id or "",
                "verify_token": config.meta_verify_token or "shadow_verify",
                "app_secret": config.meta_app_secret,
                "waba_id": config.meta_waba_id,
            }
        channel_adapter = get_adapter(config.channel_adapter, **adapter_kwargs)
        webhook_handler = WebhookHandler(adapter=channel_adapter, storage=storage)
        print(f"[main] Channel adapter initialized: {config.channel_adapter}")
    except Exception as e:
        print(f"[main] Failed to initialize channel adapter: {e}")
        channel_adapter = None
        webhook_handler = None


def _whatsapp_send_callback(msg: OutboundMessage) -> None:
    """Send outbound messages to the WhatsApp gateway."""
    import requests as _requests

    gateway_url = config.gateway_send_url
    if not gateway_url:
        print(f"[bus] No gateway URL configured, dropping message to {msg.chat_id}")
        return

    try:
        _requests.post(
            gateway_url,
            json={"to": msg.chat_id, "text": msg.content},
            timeout=10,
        )
    except Exception as e:
        print(f"[bus] Failed to send via gateway: {e}")


def _channel_send_callback(msg: OutboundMessage) -> None:
    """Send outbound messages via the channel adapter (Evolution/Meta Cloud)."""
    import asyncio

    if not channel_adapter:
        print(f"[bus] No channel adapter, dropping message to {msg.chat_id}")
        return

    phone = msg.target_phone or msg.chat_id.removeprefix("channel:")
    if not phone:
        print("[bus] No target phone for channel message")
        return

    async def _send():
        if msg.message_type == "template" and msg.template_name:
            return await channel_adapter.send_template(
                phone, msg.template_name, msg.template_params or []
            )
        return await channel_adapter.send_text(phone, msg.content)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_send())
        else:
            loop.run_until_complete(_send())
    except Exception as e:
        print(f"[bus] Channel send failed: {e}")


@app.on_event("startup")
async def startup_event():
    """Inicia componentes assíncronos."""
    global scheduler, heartbeat

    # Start MessageBus dispatcher
    bus = get_message_bus()
    bus.subscribe_outbound("whatsapp", _whatsapp_send_callback)
    if channel_adapter:
        bus.subscribe_outbound("channel", _channel_send_callback)
        print("[main] Channel bus subscriber registered")
    bus.start_dispatcher()
    print("[main] MessageBus dispatcher started")

    # Start scheduler
    scheduler = ShadowScheduler()
    await scheduler.start()
    print("[main] Scheduler started")

    # Start heartbeat
    heartbeat = HeartbeatService(storage=storage)
    heartbeat.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Para componentes assíncronos."""
    global scheduler, heartbeat

    if heartbeat:
        heartbeat.stop()
        print("[main] Heartbeat stopped")

    if scheduler:
        await scheduler.stop()
        print("[main] Scheduler stopped")

    bus = get_message_bus()
    bus.stop()


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

        # LangGraph orchestration (feature flag)
        use_langgraph = os.getenv("SHADOW_USE_LANGGRAPH", "false").lower() in {"1", "true"}
        if use_langgraph:
            from graph import run_graph
            result = run_graph(data, owner_id=data.get("owner_e164"))
            return result

        # Legacy: Processa mensagem com sessão
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


# === Channel Webhook ===

@app.get("/webhook/channel")
def webhook_channel_verify(request: Request) -> Any:
    """Verify webhook for Meta Cloud API (challenge response)."""
    if not webhook_handler:
        raise HTTPException(status_code=503, detail="Channel not configured")

    challenge = webhook_handler.handle_verification(dict(request.query_params))
    if challenge:
        return JSONResponse(content=int(challenge) if challenge.isdigit() else challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/channel")
async def webhook_channel_receive(request: Request) -> dict[str, str]:
    """Receive incoming messages from channel adapter (Evolution/Meta Cloud).

    Returns 200 immediately (Meta requires response < 5s), then processes async.
    """
    if not webhook_handler:
        return {"status": "channel_not_configured"}

    try:
        body = await request.json()
    except Exception:
        return {"status": "invalid_json"}

    headers = dict(request.headers)
    incoming = webhook_handler.parse_and_dedup(body, headers)

    if incoming is None:
        return {"status": "ignored"}

    # Process in background to respond quickly
    import asyncio

    asyncio.ensure_future(_process_channel_message(incoming))

    return {"status": "ok"}


async def _process_channel_message(incoming: ChannelIncoming) -> None:
    """Process an incoming channel message asynchronously."""
    from channels.user_resolver import UserResolver
    from channels.onboarding import handle_new_user

    try:
        # Resolve user (3-tier: lookup, auto-link, create)
        resolver = UserResolver(storage)
        resolved = resolver.resolve(
            incoming.phone,
            display_name=incoming.display_name,
            channel=channel_adapter.adapter_type if channel_adapter else "evolution",
        )

        # Block processing for blocked users
        if resolved.status == "blocked":
            return

        # Log inbound message
        if hasattr(storage, "log_channel_message"):
            storage.log_channel_message(
                user_phone=incoming.phone,
                direction="inbound",
                channel=channel_adapter.adapter_type if channel_adapter else "evolution",
                content=incoming.text,
                external_id=incoming.external_id,
            )

        # Handle new user onboarding
        if resolved.is_new and channel_adapter:
            await handle_new_user(
                incoming.phone, incoming.display_name, channel_adapter, storage
            )
            return

        # Build payload compatible with handle_message()
        scoped_storage = storage.for_owner(resolved.owner_id) if hasattr(storage, "for_owner") else storage

        payload = {
            "sender_e164": incoming.phone,
            "owner_e164": resolved.owner_id,
            "body": incoming.text,
            "chat_id": f"channel:{incoming.phone}",
            "chat_type": "direct",
            "is_owner": True,
            "should_reply": True,
            "triggered": True,
            "timestamp": incoming.timestamp,
            "sender_name": incoming.display_name,
        }

        result = handle_message(payload, scoped_storage, session_store)

        # Send reply via channel adapter
        reply = result.get("reply")
        if reply and channel_adapter:
            send_result = await channel_adapter.send_text(incoming.phone, reply)
            if not send_result.success:
                print(f"[channel] Failed to send reply to {incoming.phone}: {send_result.error}")

            # Log outbound message
            if hasattr(storage, "log_channel_message"):
                storage.log_channel_message(
                    user_phone=incoming.phone,
                    direction="outbound",
                    channel=channel_adapter.adapter_type,
                    content=reply,
                )

        # Mark as read
        if channel_adapter and incoming.external_id:
            await channel_adapter.mark_read(incoming.external_id)

    except Exception as e:
        print(f"[channel] Error processing message from {incoming.phone}: {e}")


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
