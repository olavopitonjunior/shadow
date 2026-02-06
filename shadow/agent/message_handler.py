import os
import re
import asyncio
from datetime import datetime, timezone
from typing import Any

import dateparser
import requests

from storage import Storage
from sessions import SessionStore, ContextMessage, get_session_store
from config import load_config
from contact_resolver import ContactResolver, auto_link_task_contacts
from contact_summarizer import maybe_update_contact_summary
from contact_memory import maybe_capture_memory, process_feedback_for_memories
from learning import LearningSystem
from policy import detect_prompt_injection, apply_output_guardrails, safe_refusal

# Tool system (moltbot-inspired)
from tools import (
    ToolRegistry,
    ToolContext,
    get_tool_registry,
    setup_default_tools,
)

# Initialize tool registry with default tools
_tool_registry: ToolRegistry | None = None


def _get_tool_registry() -> ToolRegistry:
    """Get or initialize the tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = setup_default_tools()
    return _tool_registry


def _run_async(coro):
    """Run async coroutine synchronously in a new event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _execute_tool(
    tool_name: str,
    params: dict[str, Any],
    storage: Storage,
    session_id: str | None = None,
    user_phone: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any] | None:
    """
    Execute a tool by name with given parameters.

    Returns tool result dict or None if tool not found.
    """
    registry = _get_tool_registry()

    if tool_name not in registry:
        return None

    context = ToolContext(
        user_phone=user_phone,
        session_id=session_id,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        storage=storage,
    )

    result = registry.execute(tool_name, params, context)
    return result.to_dict()

# Carrega configuração
_config = load_config()

# Verifica se modo é "open" (responde a qualquer um)
ACCESS_MODE_OPEN = os.getenv("SHADOW_ACCESS_MODE", "owner_only").lower() == "open"

# Entity extractor (lazy loaded)
_entity_extractor = None

# Learning system (lazy loaded)
_learning_system = None


def _get_learning_system(storage: Storage) -> LearningSystem:
    """Lazy load learning system."""
    global _learning_system
    if _learning_system is None:
        _learning_system = LearningSystem(storage)
    return _learning_system


def _get_entity_extractor():
    """Lazy load entity extractor."""
    global _entity_extractor
    if _entity_extractor is None:
        from entity_extractor import EntityExtractor
        _entity_extractor = EntityExtractor(_config.gemini_api_key)
    return _entity_extractor

# URL do gateway para criar grupo Shadow
GATEWAY_URL = os.getenv("SHADOW_GATEWAY_URL", "http://localhost:18790")

# Comandos de onboarding
ONBOARDING_COMMANDS = {"setup", "iniciar", "começar", "start", "configurar"}
ONBOARDING_CONFIRM = {"confirmar", "confirm", "ok", "pronto", "feito", "done"}


def _create_shadow_group() -> dict[str, Any]:
    """Chama o gateway para criar o grupo Shadow."""
    try:
        response = requests.post(f"{GATEWAY_URL}/create-shadow-group", timeout=30)
        if response.status_code == 200:
            return response.json()
        return {"error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

TASK_PATTERNS = [
    r"^tarefa[:\s]+(.+)$",
    r"^cria(?:r)? tarefa[:\s]+(.+)$",
    r"^adiciona(?:r)? tarefa[:\s]+(.+)$",
]

APPOINTMENT_PATTERNS = [
    r"^reuni[a�]o[:\s]+(.+)$",
    r"^agenda(?:r)?[:\s]+(.+)$",
    r"^compromisso[:\s]+(.+)$",
]

REMINDER_PATTERNS = [
    r"^lembrete[:\s]+(.+)$",
    r"^me lembra[:\s]+(.+)$",
    r"^lembrar[:\s]+(.+)$",
]

# Query patterns for entity/context queries
CONTACT_CONTEXT_PATTERNS = [
    r"(?:contexto|historico|conversa).*(?:com|do|da)\s+(.+)$",
    r"(?:o que|que).*(?:falamos|conversamos).*(?:com|sobre)\s+(.+)$",
    r"(?:resumo|resumir).*(?:conversa|papo).*(?:com|do|da)\s+(.+)$",
]

TASKS_FOR_CONTACT_PATTERNS = [
    r"tarefas.*(?:do|da|com|para)\s+(.+)$",
    r"(?:o que|que).*(?:preciso|tenho que).*(?:fazer|enviar).*(?:para|com)\s+(.+)$",
    r"pendencias.*(?:do|da|com)\s+(.+)$",
]

TODAY_TASKS_PATTERNS = [
    r"(?:quais|minhas).*tarefas.*(?:hoje|dia)",
    r"tarefas.*(?:hoje|dia)",
    r"(?:pendencias|pendentes).*(?:hoje|dia)",
    r"(?:o que|que).*(?:tenho|preciso).*(?:fazer|hoje)",
]


def _parse_datetime(text: str) -> str | None:
    if not text:
        return None
    dt = dateparser.parse(
        text,
        languages=["pt"],
        settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False},
    )
    if not dt:
        return None
    return dt.isoformat()


def _match_pattern(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _match_any_pattern(patterns: list[str], text: str) -> tuple[bool, str | None]:
    """Match any pattern, returning (matched, captured_group)."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return (True, match.group(1).strip() if match.lastindex else None)
            except IndexError:
                return (True, None)
    return (False, None)


def _extract_and_store_entities(
    storage: Storage,
    owner_id: str,
    message: str,
    chat_id: str,
    message_id: str | None,
    sender_name: str | None,
    sender_phone: str | None,
    chat_type: str,
    session: Any,
    session_store: SessionStore | None,
) -> None:
    """Extract entities from message and store them (runs synchronously)."""
    extractor = _get_entity_extractor()
    if not extractor:
        return

    # Build context
    recent_messages = []
    if session_store and session:
        context_msgs = session_store.get_context(session.id, limit=5)
        recent_messages = [{"role": m.role, "content": m.content} for m in context_msgs]

    chat_context = {
        "sender_name": sender_name or "Desconhecido",
        "sender_phone": sender_phone,
        "chat_type": chat_type,
        "recent_messages": recent_messages,
    }

    # Run extraction (sync wrapper for async)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(extractor.extract(message, chat_context))
        loop.close()
    except Exception:
        # Fallback to basic extraction
        result = extractor._extract_basic(message, chat_context)

    # Store extracted entities and auto-link tasks to contacts
    for entity in result.entities:
        entity_id = storage.save_extracted_entity(
            owner_id=owner_id,
            source_chat_id=chat_id,
            source_message_id=message_id,
            entity_type=entity.entity_type,
            entity_data=entity.data,
            confidence=entity.confidence,
        )

        # Auto-link tasks to contacts (Phase 2)
        if entity.entity_type == "task" and entity_id:
            try:
                # Create actual task from extracted entity
                task = storage.create_task(
                    title=entity.data.get("description", ""),
                    due_at=entity.data.get("due_date"),
                )
                # Link task to relevant contacts
                auto_link_task_contacts(
                    storage=storage,
                    owner_id=owner_id,
                    task_id=task.id,
                    entity_data=entity.data,
                    sender_phone=sender_phone,
                    message_text=message,
                )
            except Exception:
                pass  # Don't fail extraction if auto-link fails

    # Update contact context
    if sender_phone and sender_phone != owner_id:
        storage.update_contact_context(
            owner_id=owner_id,
            contact_phone=sender_phone,
            contact_name=sender_name,
            message=message,
        )

        # Phase 3: Auto-update summary if threshold reached
        try:
            maybe_update_contact_summary(
                storage=storage,
                owner_id=owner_id,
                contact_phone=sender_phone,
                contact_name=sender_name,
                api_key=_config.gemini_api_key if _config else None,
            )
        except Exception:
            pass  # Don't fail message processing if summarization fails

        # Phase 6: Auto-capture memories (preferences, facts, decisions)
        try:
            import os
            maybe_capture_memory(
                storage=storage,
                owner_id=owner_id,
                contact_phone=sender_phone,
                message=message,
                openai_key=os.getenv("OPENAI_API_KEY"),
            )
        except Exception:
            pass  # Don't fail message processing if memory capture fails


def _format_today_tasks(tasks: list[dict[str, Any]]) -> str:
    """Format today's tasks for display."""
    if not tasks:
        return "Nenhuma tarefa para hoje."

    lines = ["Tarefas para hoje:"]
    for i, task in enumerate(tasks, 1):
        title = task.get("title", "Sem titulo")
        due = task.get("due_at") or task.get("due_date") or ""
        contacts = task.get("contacts", [])

        line = f"{i}. {title}"
        if due:
            time_part = due.split("T")[1][:5] if "T" in due else ""
            if time_part:
                line += f" (ate {time_part})"

        if contacts:
            contact_names = [c.get("contact_name") or c.get("contact_phone") for c in contacts if c.get("contact_name") or c.get("contact_phone")]
            if contact_names:
                line += f" - {', '.join(contact_names)}"

        if task.get("status") == "extracted":
            line += " [extraido]"

        lines.append(line)

    return "\n".join(lines)


def _format_contact_context(context: dict[str, Any] | None, contact_name: str) -> str:
    """Format contact context for display."""
    if not context:
        return f"Nao encontrei informacoes sobre '{contact_name}'."

    name = context.get("contact_name") or context.get("contact_phone") or contact_name
    phone = context.get("contact_phone", "N/A")
    last = context.get("last_interaction", "N/A")
    count = context.get("interaction_count", 0)
    msg_count = context.get("message_count", 0)
    summary = context.get("summary") or "Sem resumo disponivel"
    topics = context.get("topics") or []

    lines = [
        f"Contexto com {name}:",
        f"Telefone: {phone}",
        f"Ultima interacao: {last[:10] if last != 'N/A' else 'N/A'}",
        f"Total de interacoes: {count}",
        f"Mensagens trocadas: {msg_count}",
        "",
        f"Resumo: {summary}",
    ]

    if topics:
        lines.append(f"Topicos: {', '.join(topics[:5])}")

    return "\n".join(lines)


def _format_tasks_for_contact(tasks: list[dict[str, Any]], contact_name: str) -> str:
    """Format tasks for a specific contact."""
    if not tasks:
        return f"Nenhuma tarefa relacionada a '{contact_name}'."

    lines = [f"Tarefas relacionadas a {contact_name}:"]
    for i, task in enumerate(tasks, 1):
        title = task.get("title", "Sem titulo")
        due = task.get("due_at") or task.get("due_date") or ""
        status = task.get("status", "pending")

        line = f"{i}. {title}"
        if due:
            line += f" (ate {due[:10]})"
        if status == "extracted":
            line += " [extraido]"

        lines.append(line)

    return "\n".join(lines)


def _record_response(
    session_store: SessionStore | None,
    session_id: str | None,
    reply: str,
    intent: str,
) -> None:
    """Registra resposta do assistente no contexto da sessão."""
    if session_store and session_id and reply:
        session_store.add_message(session_id, ContextMessage(
            role="assistant",
            content=reply,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={"intent": intent},
        ))


def _track_recipient(
    session_store: SessionStore | None,
    session_id: str | None,
    channel: str,
    recipient: str | None,
) -> None:
    """
    Track recipient for future message resolution (Phase 4).

    This enables intelligent recipient resolution for reminders and
    future messages based on conversation history.
    """
    if session_store and session_id and recipient:
        session_store.update_last_recipient(
            session_id=session_id,
            channel=channel,
            recipient=recipient,
        )


def _build_summary(storage: Storage) -> str:
    tasks = storage.list_tasks(20)
    appointments = storage.list_appointments(20)
    lines = ["Resumo do dia:"]
    if tasks:
        lines.append("Tarefas pendentes:")
        for task in tasks[:5]:
            suffix = f" (ate {task.due_at})" if task.due_at else ""
            lines.append(f"- {task.title}{suffix}")
    else:
        lines.append("Sem tarefas pendentes.")
    if appointments:
        lines.append("Compromissos:")
        for appt in appointments[:5]:
            lines.append(f"- {appt.title} ({appt.scheduled_at})")
    else:
        lines.append("Sem compromissos agendados.")
    return "\n".join(lines)


def handle_message(
    payload: dict[str, Any],
    storage: Storage,
    session_store: SessionStore | None = None,
) -> dict[str, Any]:
    """
    Processa mensagem e retorna resposta.

    Args:
        payload: Dados da mensagem recebida
        storage: Storage para persistência
        session_store: SessionStore para contexto (opcional)
    """
    body = (payload.get("body") or payload.get("content") or "").strip()
    sender = payload.get("sender_e164") or payload.get("contact_phone")
    sender_name = payload.get("sender_name")
    owner = payload.get("owner_e164") or payload.get("user_phone")
    is_owner = payload.get("is_owner") if payload.get("is_owner") is not None else sender == owner
    chat_id = payload.get("chat_id") or payload.get("metadata", {}).get("remoteJid")
    chat_type = payload.get("chat_type") or "direct"
    should_reply = payload.get("should_reply")

    # Phase 7B: Transcrever áudio se presente
    media_type = payload.get("media_type")
    media_url = payload.get("media_url")
    media_mime_type = payload.get("media_mime_type")

    if media_type == "audio" and media_url:
        try:
            from media import get_media_processor
            processor = get_media_processor()
            result = _run_async(
                processor.process_audio(url=media_url, mime_type=media_mime_type or "audio/ogg")
            )
            if result.success and result.text:
                body = result.text.strip()
                print(f"[audio] Transcrito: {body[:50]}...")
        except Exception as e:
            print(f"[audio] Erro na transcrição: {e}")

    # Obtém ou cria sessão para contexto
    session = None
    if session_store and chat_id:
        kind = "group" if "@g.us" in (chat_id or "") else "direct"
        session = session_store.get_or_create(
            chat_id=chat_id,
            participant_phone=sender,
            kind=kind,
            display_name=sender_name,
        )
        # Adiciona mensagem do usuário ao contexto
        if body:
            session_store.add_message(session.id, ContextMessage(
                role="user",
                content=body,
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={"sender": sender, "intent": "pending"},
            ))

    if body:
        storage.ingest_message(chat_id, chat_type, sender, sender_name, body, "inbound", bool(is_owner))

        # Entity extraction for ALL contact messages (Shadow reads everything)
        # Extract from contacts (not owner) to build context and identify tasks
        if body and sender and not is_owner:
            try:
                _extract_and_store_entities(
                    storage=storage,
                    owner_id=owner,
                    message=body,
                    chat_id=chat_id,
                    message_id=payload.get("message_id"),
                    sender_name=sender_name,
                    sender_phone=sender,
                    chat_type=chat_type,
                    session=session,
                    session_store=session_store,
                )
            except Exception as e:
                # Don't fail message processing if extraction fails
                pass

    if not body:
        return {"reply": None, "intent": "none", "actions": [], "session_id": session.id if session else None}

    # Se access mode é "open", responde a qualquer um; senão apenas ao owner
    if not ACCESS_MODE_OPEN and not is_owner:
        return {"reply": None, "intent": "ingest", "actions": [], "session_id": session.id if session else None}

    if should_reply is False:
        return {"reply": None, "intent": "silent", "actions": [], "session_id": session.id if session else None}

    lower = body.lower()
    session_id = session.id if session else None

    # Guardrail: prompt injection detection (block tool usage)
    injection = detect_prompt_injection(body)
    if not injection.allowed:
        return {
            "reply": safe_refusal(injection.reason),
            "intent": "blocked",
            "actions": [],
            "session_id": session_id,
        }

    # Phase 5 Learning: Detect and process feedback
    try:
        learning = _get_learning_system(storage)
        feedback = learning.detect_feedback(body)
        if feedback:
            # Record feedback for learning
            learning.record_feedback(
                owner_id=owner,
                feedback=feedback,
                message_id=payload.get("message_id"),
            )
            # Process memory promotion/demotion
            # Note: memory_ids_used would need to be tracked from previous response
            # For now, we just record the feedback for future use
            openai_key = os.getenv("OPENAI_API_KEY")
            if feedback.rating in ("positive", "negative", "correction"):
                try:
                    # This would require tracking which memories were used
                    # For now, just log the feedback
                    print(f"[learning] Feedback recorded: {feedback.rating}")
                except Exception:
                    pass
    except Exception as e:
        print(f"[learning] Feedback detection error: {e}")

    # Helper para retornar resultado e registrar no contexto
    def make_result(reply: str, intent: str, actions: list[str] | None = None) -> dict[str, Any]:
        safe_reply = apply_output_guardrails(reply)
        storage.record_interaction(sender, body, safe_reply, intent)
        _record_response(session_store, session_id, safe_reply, intent)
        # Track recipient for future message resolution (Phase 4)
        if safe_reply and sender:
            _track_recipient(session_store, session_id, "whatsapp", sender)
        return {
            "reply": safe_reply,
            "intent": intent,
            "actions": actions or [],
            "session_id": session_id,
        }

    # Onboarding: criar grupo Shadow automaticamente (2 etapas)
    if lower in ONBOARDING_COMMANDS and is_owner:
        shadow_group_jid = storage.get_shadow_group_jid()
        if shadow_group_jid:
            reply = f"Grupo Shadow ja existe! Envie suas mensagens para o grupo Shadow no WhatsApp."
            return make_result(reply, "onboarding_exists")

        # Etapa 1: Mostrar instrução sobre adicionar contato
        storage.set_config("onboarding_pending", "true")
        reply = (
            "Antes de criar o grupo Shadow, voce precisa:\n\n"
            "1. Salvar seu proprio numero nos contatos do WhatsApp\n"
            "   (Abra Contatos > Adicionar > Digite seu numero)\n\n"
            "Isso e necessario para que as mensagens sejam descriptografadas corretamente.\n\n"
            "Apos adicionar o contato, digite 'confirmar' para criar o grupo Shadow."
        )
        return make_result(reply, "onboarding_pending")

    # Etapa 2: Confirmar e criar grupo
    if lower in ONBOARDING_CONFIRM and is_owner:
        onboarding_pending = storage.get_config("onboarding_pending")
        if onboarding_pending != "true":
            reply = "Nenhum setup pendente. Digite 'setup' para iniciar a configuracao."
            return make_result(reply, "onboarding_not_pending")

        shadow_group_jid = storage.get_shadow_group_jid()
        if shadow_group_jid:
            storage.set_config("onboarding_pending", "false")
            reply = f"Grupo Shadow ja existe! Envie suas mensagens para o grupo Shadow no WhatsApp."
            return make_result(reply, "onboarding_exists")

        # Criar grupo Shadow
        result = _create_shadow_group()
        if result.get("success"):
            group_jid = result["groupJid"]
            storage.set_shadow_group_jid(group_jid)
            storage.set_config("onboarding_pending", "false")
            reply = (
                "Grupo Shadow criado com sucesso!\n\n"
                "Agora voce pode conversar comigo pelo grupo 'Shadow' no seu WhatsApp.\n"
                "Todas as mensagens enviadas la serao processadas normalmente.\n\n"
                "Comandos disponiveis:\n"
                "- criar tarefa: descricao\n"
                "- lembrete: mensagem em data/hora\n"
                "- agenda: compromisso em data/hora\n"
                "- mostrar tarefas\n"
                "- ajuda"
            )
            return make_result(reply, "onboarding_complete", ["shadow_group_created"])
        else:
            error = result.get("error", "Erro desconhecido")
            reply = f"Erro ao criar grupo Shadow: {error}\nTente novamente com 'confirmar'."
            return make_result(reply, "onboarding_error")

    if lower in {"/ping", "ping"}:
        return make_result("Shadow online.", "ping")

    if lower in {"/help", "ajuda", "help"}:
        reply = (
            "Posso ajudar com tarefas, lembretes e compromissos.\n"
            "Exemplos:\n"
            "- cria tarefa: ligar para o Joao amanha 10h\n"
            "- lembrete: cobrar contrato sexta 14h\n"
            "- reuniao: call com Carla quinta 15h\n"
            "- mostrar tarefas\n"
            "- resumo do dia\n"
            "- contexto (ver historico)"
        )
        return make_result(reply, "help")

    # Novo comando: ver contexto da sessão
    if lower in {"/contexto", "contexto", "historico"}:
        if session_store and session_id:
            context = session_store.get_context(session_id, limit=5)
            if context:
                lines = ["Ultimas mensagens:"]
                for msg in context:
                    role = "Voce" if msg.role == "user" else "Shadow"
                    lines.append(f"[{role}]: {msg.content[:50]}...")
                reply = "\n".join(lines)
            else:
                reply = "Sem historico de conversa."
        else:
            reply = "Sessao nao disponivel."
        return make_result(reply, "context")

    if "resumo do dia" in lower or "resumo" == lower:
        return make_result(_build_summary(storage), "daily_summary")

    if "mostrar tarefas" in lower or "tarefas" == lower:
        tasks = storage.list_tasks()
        if not tasks:
            reply = "Nao ha tarefas pendentes."
        else:
            lines = ["Tarefas pendentes:"]
            for task in tasks:
                suffix = f" (ate {task.due_at})" if task.due_at else ""
                lines.append(f"- {task.title}{suffix}")
            reply = "\n".join(lines)
        return make_result(reply, "list_tasks")

    # Query: tarefas do dia / tarefas de hoje
    matched, _ = _match_any_pattern(TODAY_TASKS_PATTERNS, lower)
    if matched:
        tasks = storage.list_today_tasks_with_contacts(owner)
        reply = _format_today_tasks(tasks)
        return make_result(reply, "list_today_tasks")

    # Query: contexto/historico com contato X
    matched, contact_name = _match_any_pattern(CONTACT_CONTEXT_PATTERNS, body)
    if matched and contact_name:
        context = storage.get_contact_context(owner, contact_name=contact_name)
        if not context:
            # Try by phone
            context = storage.get_contact_context(owner, contact_phone=contact_name)
        reply = _format_contact_context(context, contact_name)

        # Also get recent messages
        messages = storage.search_conversations_with_contact(owner, contact_name, limit=5)
        if messages:
            reply += "\n\nUltimas mensagens:"
            for msg in messages[:5]:
                direction = "Voce" if msg.get("direction") == "outbound" else msg.get("contact_name", "Contato")
                content = msg.get("content", "")[:50]
                reply += f"\n[{direction}]: {content}..."

        return make_result(reply, "contact_context")

    # Query: tarefas do/para contato X
    matched, contact_name = _match_any_pattern(TASKS_FOR_CONTACT_PATTERNS, body)
    if matched and contact_name:
        tasks = storage.list_tasks_for_contact(owner, contact_name)
        reply = _format_tasks_for_contact(tasks, contact_name)
        return make_result(reply, "tasks_for_contact")

    if "agenda" in lower or "compromissos" in lower:
        appointments = storage.list_appointments()
        if not appointments:
            reply = "Nao ha compromissos agendados."
        else:
            lines = ["Proximos compromissos:"]
            for appt in appointments:
                lines.append(f"- {appt.title} ({appt.scheduled_at})")
            reply = "\n".join(lines)
        return make_result(reply, "list_appointments")

    task_text = _match_pattern(TASK_PATTERNS, body)
    if task_text:
        # Use Tool System for create_task
        result = _execute_tool(
            "create_task",
            {"title": task_text, "due_date": task_text},  # Let tool parse date
            storage=storage,
            session_id=session_id,
            user_phone=sender,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        if result and result.get("success"):
            reply = result.get("display_text") or f"Tarefa criada: {task_text}"
            return make_result(reply, "create_task", ["task_created"])
        else:
            # Fallback to direct storage call
            due_at = _parse_datetime(task_text)
            task = storage.create_task(task_text, due_at)
            reply = f"Tarefa criada: {task.title}"
            if due_at:
                reply += f" (ate {due_at})"
            return make_result(reply, "create_task", ["task_created"])

    appt_text = _match_pattern(APPOINTMENT_PATTERNS, body)
    if appt_text:
        scheduled_at = _parse_datetime(appt_text)
        if not scheduled_at:
            return make_result("Preciso da data/horario para agendar o compromisso.", "ask_schedule")
        appt = storage.create_appointment(appt_text, scheduled_at)
        reply = f"Compromisso criado: {appt.title} em {appt.scheduled_at}"
        return make_result(reply, "create_appointment", ["appointment_created"])

    reminder_text = _match_pattern(REMINDER_PATTERNS, body)
    if reminder_text:
        remind_at = _parse_datetime(reminder_text)
        if not remind_at:
            return make_result("Preciso da data/horario para o lembrete.", "ask_reminder_time")
        storage.create_reminder(remind_at, reminder_text)
        reply = f"Lembrete criado para {remind_at}."
        return make_result(reply, "create_reminder", ["reminder_created"])

    # Phase 8: ReAct Agent (Claude) - Full agentic loop with tool use
    try:
        from react_agent import get_react_agent, AgentStatus

        agent = get_react_agent()

        # Check if message can use fast-path (handled above by regex)
        if not agent.should_use_fast_path(body):
            # Build tool context
            tool_context = ToolContext(
                user_phone=owner,
                session_id=session_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                storage=storage,
            )

            # Run ReAct loop
            state = agent.run(body, tool_context)

            if state.status == AgentStatus.DONE and state.final_response:
                # Use last tool name as intent, or "agent_response" if no tools used
                intent = state.last_tool or "agent_response"
                return make_result(state.final_response, intent)

            if state.status == AgentStatus.ERROR and state.final_response:
                return make_result(state.final_response, "agent_error")

    except Exception as e:
        print(f"[react_agent] Error: {e}")
        import traceback
        traceback.print_exc()

    # Fallback original
    return make_result("Anotado. Se quiser criar tarefas ou lembretes, me diga diretamente.", "note")
