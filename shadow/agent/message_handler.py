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

# URL do gateway para criar grupo Shadow e enviar mensagens
GATEWAY_URL = os.getenv("SHADOW_GATEWAY_URL", "http://localhost:18790")
GATEWAY_SEND_URL = os.getenv("SHADOW_GATEWAY_SEND_URL", f"{GATEWAY_URL}/send")

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


def _send_to_shadow_group(storage: Storage, message: str) -> bool:
    """
    Envia mensagem para o Grupo Shadow via gateway (Phase 8 - CRM Oculto).

    Todas as comunicações do Shadow com o owner devem ir para o grupo dedicado.
    Se o grupo não existir, tenta criar um novo.
    """
    try:
        # Get Shadow group JID from storage
        group_jid = storage.get_shadow_group_jid()

        if not group_jid:
            # Try to create the group
            print("[send_to_shadow] No Shadow group found, attempting to create...")
            result = _create_shadow_group()
            if "error" in result:
                print(f"[send_to_shadow] Failed to create group: {result['error']}")
                return False

            group_jid = result.get("groupJid")  # Gateway returns "groupJid", not "groupId"
            if group_jid:
                storage.set_shadow_group_jid(group_jid)
                print(f"[send_to_shadow] Created Shadow group: {group_jid}")
            else:
                print("[send_to_shadow] No group JID in response")
                return False

        payload = {
            "to": group_jid,
            "text": message,
        }

        response = requests.post(GATEWAY_SEND_URL, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"[send_to_shadow] Failed: HTTP {response.status_code} - {response.text}")
        return response.status_code == 200

    except Exception as e:
        print(f"[send_to_shadow] Error: {e}")
        return False


def _is_valid_e164(phone: str | None) -> bool:
    """
    Check if phone looks like valid E.164, not a LID or JID.

    LID pattern: ends with @lid, typically 14+ digits starting with 0 or 4
    JID pattern: ends with @s.whatsapp.net
    E.164 pattern: country code (1-3) + number (7-12) = 10-13 digits
    Brazilian: 55 + DDD(2) + number(8-9) = 12-13 digits
    """
    if not phone:
        return False
    # Explicit LID/JID check - these are NOT valid phones
    phone_lower = phone.lower()
    if "@lid" in phone_lower or "@s.whatsapp.net" in phone_lower:
        return False
    # Extract digits only
    digits = phone.replace("+", "").split("@")[0].split(":")[0]
    # LIDs are typically 14+ digits, E.164 is max 13
    if len(digits) >= 14:
        return False
    # LIDs often start with 0
    if digits.startswith("0"):
        return False
    # Valid phone: all digits, 10-13 chars (country code + number)
    return digits.isdigit() and 10 <= len(digits) <= 13


def _format_appointment_confirmation(
    entity_data: dict[str, Any],
    sender_name: str | None,
    sender_phone: str | None,
) -> str:
    """
    Formata mensagem de confirmação para compromisso detectado.

    Quando o Shadow detecta um compromisso em conversa de terceiros,
    ele pergunta ao owner se deve registrar.
    """
    title = entity_data.get("title") or entity_data.get("description") or "Compromisso"
    date_str = entity_data.get("datetime") or entity_data.get("scheduled_at") or "não especificado"

    # Format date nicely
    if date_str and date_str != "não especificado":
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_str = dt.strftime("%d/%m/%Y às %H:%M")
        except Exception:
            pass

    # Build contact info - graceful handling when phone unavailable
    contact_info = sender_name or "Contato"
    if sender_phone and sender_phone != sender_name and _is_valid_e164(sender_phone):
        # Clean phone for display
        phone_display = sender_phone
        if "@" in phone_display:
            phone_display = phone_display.split("@")[0]
        if not phone_display.startswith("+"):
            phone_display = f"+{phone_display}"
        contact_info = f"{sender_name or 'Contato'} ({phone_display})"
    # else: just use name, no corrupted phone display

    return (
        f"📅 *Compromisso detectado*\n\n"
        f"Com: {contact_info}\n"
        f"O quê: {title}\n"
        f"Quando: {date_str}\n\n"
        f"Quer que eu registre e crie um lembrete?\n"
        f"Responda *Sim* ou *Não*"
    )


def _detect_confirmation_response(message: str) -> str | None:
    """
    Detecta se a mensagem é uma resposta a confirmação pendente.

    Retorna "yes", "no", ou None se não reconheceu.
    """
    msg = message.lower().strip()

    # Positive responses
    if msg in ["sim", "s", "yes", "y", "ok", "pode", "registra", "1", "aceito", "aceitar"]:
        return "yes"

    # Negative responses
    if msg in ["não", "nao", "n", "no", "cancela", "descarta", "2", "ignorar", "ignora"]:
        return "no"

    return None


def _execute_pending_action(
    pending,  # PendingConfirmation
    storage: Storage,
    owner_phone: str,
    session_id: str | None,
) -> str:
    """
    Executa a ação de uma confirmação pendente aceita.

    Cria o compromisso/tarefa e retorna mensagem de sucesso.
    """
    entity_data = pending.entity_data
    confirmation_type = pending.confirmation_type

    if confirmation_type == "create_appointment":
        # Create appointment
        title = entity_data.get("title") or entity_data.get("description") or "Compromisso"
        scheduled_at = entity_data.get("datetime") or entity_data.get("scheduled_at")

        if not scheduled_at:
            return "Não consegui identificar a data do compromisso. Tente novamente com: agenda: [descrição] [data/hora]"

        appt = storage.create_appointment(title, scheduled_at)

        # Also create a reminder 30 min before
        try:
            from datetime import datetime, timedelta
            dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            remind_at = (dt - timedelta(minutes=30)).isoformat()
            storage.create_reminder(remind_at, f"Lembrete: {title}")
        except Exception:
            pass

        # Format response
        contact_info = ""
        if pending.sender_name:
            contact_info = f" com {pending.sender_name}"

        return f"✅ Compromisso registrado: {title}{contact_info}\nLembrete criado para 30 minutos antes."

    elif confirmation_type == "create_task":
        # Create task
        title = entity_data.get("title") or entity_data.get("description") or "Tarefa"
        due_at = entity_data.get("due_date") or entity_data.get("datetime")

        task = storage.create_task(title, due_at)
        return f"✅ Tarefa registrada: {title}"

    return "Ação executada."


def _should_extract_entities(
    storage: Storage,
    owner_id: str,
    chat_type: str,
    chat_id: str | None,
) -> bool:
    """
    Decide if we should extract entities from this message.

    For private chats: always extract
    For groups: check user settings (group_monitoring_enabled) and monitored list

    Args:
        storage: Storage instance
        owner_id: Owner phone E.164
        chat_type: "direct" or "group"
        chat_id: WhatsApp chat JID

    Returns:
        True if should extract entities, False otherwise
    """
    # Always extract from private/direct chats
    if chat_type == "direct" or (chat_id and "@s.whatsapp.net" in chat_id):
        return True

    # For groups, check user settings
    if not chat_id:
        return False

    try:
        settings = storage.get_user_settings(owner_id)

        # Check if group monitoring is enabled globally
        group_monitoring = settings.get("group_monitoring_enabled", 0)
        if group_monitoring:
            return True

        # Check if this specific group is in the monitored list
        monitored_groups = storage.get_monitored_groups(owner_id)
        if chat_id in monitored_groups:
            return True

        # Also check without @g.us suffix for flexibility
        chat_base = chat_id.split("@")[0] if "@" in chat_id else chat_id
        for group in monitored_groups:
            group_base = group.split("@")[0] if "@" in group else group
            if chat_base == group_base:
                return True

        return False

    except Exception as e:
        print(f"[extract] Error checking group settings: {e}")
        # Default to NOT extracting on error (safer)
        return False


def _check_immediate_suggestion(
    entities: list,
    sender_phone: str | None,
    sender_name: str | None,
    owner_phone: str,
    chat_id: str | None,
    session_store,
    storage: Storage | None = None,
) -> bool:
    """
    Verifica se alguma entidade extraída precisa de confirmação imediata.

    Quando detecta um compromisso/reunião, pergunta IMEDIATAMENTE ao owner
    via Grupo Shadow (toda comunicação do Shadow fica em um único lugar).

    Tarefas vão para a fila de sugestões (não pergunta inline).

    Retorna True se enviou pergunta de confirmação.

    Note: This is intentionally sync - _send_to_shadow_group uses requests which is blocking.
    """
    if not session_store or not storage:
        return False

    for entity in entities:
        entity_type = entity.entity_type if hasattr(entity, 'entity_type') else entity.get('entity_type')
        entity_data = entity.data if hasattr(entity, 'data') else entity.get('data', {})

        # Only immediate confirmation for appointments/meetings
        if entity_type in ["meeting", "appointment"]:
            # Format and send confirmation message to Shadow group
            msg = _format_appointment_confirmation(entity_data, sender_name, sender_phone)
            sent = _send_to_shadow_group(storage, msg)

            if sent:
                # Store pending confirmation
                session_store.set_pending_confirmation(
                    owner_id=owner_phone,
                    confirmation_type="create_appointment",
                    entity_data=entity_data,
                    sender_phone=sender_phone,
                    sender_name=sender_name,
                    source_chat_id=chat_id,
                    expires_in_seconds=300,  # 5 minutes
                )
                print(f"[immediate] Sent appointment confirmation to Shadow group")
                return True

    return False


def _update_contact_context_with_entities(
    storage: Storage,
    owner_id: str,
    contact_phone: str,
    entities: list,
) -> None:
    """
    Update contact context with information extracted from entities.

    Phase 8F: Context update contínuo.
    When entities are extracted from a conversation, update the contact's
    context with relevant information (email, company, preferences, etc).
    """
    if not entities or not contact_phone:
        return

    context_updates = {}
    topics_to_add = []

    for entity in entities:
        entity_type = entity.entity_type if hasattr(entity, 'entity_type') else entity.get('entity_type')
        entity_data = entity.data if hasattr(entity, 'data') else entity.get('data', {})

        if entity_type == "meeting" or entity_type == "appointment":
            # Contact has pending appointments
            context_updates["has_pending_appointments"] = True
            topics_to_add.append("reuniões")

        elif entity_type == "task":
            # Contact has pending tasks
            context_updates["has_pending_tasks"] = True
            topics_to_add.append("tarefas")

        elif entity_type == "contact":
            # Contact info extracted - update profile data
            if entity_data.get("email"):
                context_updates["email"] = entity_data["email"]
            if entity_data.get("company") or entity_data.get("empresa"):
                context_updates["company"] = entity_data.get("company") or entity_data.get("empresa")
            if entity_data.get("role") or entity_data.get("cargo"):
                context_updates["role"] = entity_data.get("role") or entity_data.get("cargo")
            if entity_data.get("nickname") or entity_data.get("apelido"):
                # Add alias
                nickname = entity_data.get("nickname") or entity_data.get("apelido")
                try:
                    storage.add_contact_alias(owner_id, contact_phone, nickname)
                except Exception:
                    pass

        elif entity_type == "reminder":
            topics_to_add.append("lembretes")

    # Update context if we have changes
    if context_updates or topics_to_add:
        try:
            # Get current context
            current = storage.get_contact_context(owner_id, contact_phone=contact_phone)
            if current:
                # Merge topics
                current_topics = current.get("topics") or []
                if isinstance(current_topics, str):
                    import json
                    try:
                        current_topics = json.loads(current_topics)
                    except Exception:
                        current_topics = []

                # Add new topics (avoid duplicates)
                for topic in topics_to_add:
                    if topic not in current_topics:
                        current_topics.append(topic)

                # Keep only last 10 topics
                context_updates["topics"] = current_topics[-10:]

            # Update the context
            storage.update_contact_context_fields(owner_id, contact_phone, context_updates)
            print(f"[context] Updated context for {contact_phone}: {list(context_updates.keys())}")

        except Exception as e:
            print(f"[context] Error updating context: {e}")


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
    """Parse date/time from text, including mixed text with non-date words."""
    if not text:
        return None

    _dp_settings = {"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False}

    # 1) Try full text first
    dt = dateparser.parse(text, languages=["pt"], settings=_dp_settings)
    if dt:
        return dt.isoformat()

    # 2) Extract date fragments from mixed text using known Portuguese patterns
    lower = text.lower()
    date_keywords = re.findall(
        r"(?:hoje|amanh[aã]|depois de amanh[aã]|"
        r"pr[oó]xim[oa]\s+\w+|"
        r"segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo|"
        r"em\s+\d+\s+(?:minutos?|horas?|dias?|semanas?)|"
        r"\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
        lower,
    )
    if date_keywords:
        date_str = " ".join(date_keywords)
        dt = dateparser.parse(date_str, languages=["pt"], settings=_dp_settings)
        if dt:
            # Extract explicit time (e.g. "14h", "às 15h", "10:30", "às 10")
            time_match = re.search(r"(?:[àa]s?\s+)(\d{1,2})\s*[h:]?\s*(\d{0,2})", lower)
            if not time_match:
                time_match = re.search(r"(\d{1,2})\s*[h:]\s*(\d{0,2})", lower)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return dt.isoformat()

    return None


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
):
    """Extract entities from message and store them (runs synchronously).

    Returns the extraction result for immediate suggestion checking.
    """
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
            sender_phone=sender_phone,  # Phase 7: Real sender phone for contact association
            sender_name=sender_name,    # Phase 7: Real sender name (push name)
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

    return result


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
    sender_jid = payload.get("sender_jid")  # Fallback when E.164 resolution fails
    sender_name = payload.get("sender_name")
    owner = payload.get("owner_e164") or payload.get("user_phone")
    is_owner = payload.get("is_owner") if payload.get("is_owner") is not None else sender == owner
    chat_id = payload.get("chat_id") or (payload.get("metadata") or {}).get("remoteJid")
    chat_type = payload.get("chat_type") or "direct"
    should_reply = payload.get("should_reply")
    monitor_only = payload.get("monitor_only", False)  # Phase 7: Monitored messages

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

        # Entity extraction for contact messages (respects group monitoring settings)
        # Extract from contacts (not owner) to build context and identify tasks
        # Phase 7: Also extract from monitored messages even when sender_e164 is null
        # Phase 8: Respect group monitoring settings - only extract from monitored groups
        sender_identifier = sender or sender_jid  # Use JID as fallback
        should_extract = (
            body
            and sender_identifier
            and not is_owner
            and _should_extract_entities(storage, owner, chat_type, chat_id)
        )
        if should_extract:
            try:
                extraction_result = _extract_and_store_entities(
                    storage=storage,
                    owner_id=owner,
                    message=body,
                    chat_id=chat_id,
                    message_id=payload.get("message_id"),
                    sender_name=sender_name,
                    sender_phone=sender_identifier,  # Can be phone or JID
                    chat_type=chat_type,
                    session=session,
                    session_store=session_store,
                )
                if monitor_only:
                    print(f"[entity] Extracted from monitored message: {body[:50]}...")

                # Phase 8: Check for immediate suggestions (appointments)
                # Send confirmation to owner if meeting/appointment detected
                if owner and extraction_result and extraction_result.entities:
                    try:
                        sent_confirmation = _check_immediate_suggestion(
                            entities=extraction_result.entities,
                            sender_phone=sender_identifier,
                            sender_name=sender_name,
                            owner_phone=owner,
                            chat_id=chat_id,
                            session_store=session_store,
                            storage=storage,
                        )
                        if sent_confirmation:
                            print(f"[immediate] Sent confirmation request to Shadow group for appointment")
                    except Exception as e:
                        print(f"[immediate] Error checking immediate suggestions: {e}")

                    # Phase 8F: Update contact context with entity info
                    try:
                        _update_contact_context_with_entities(
                            storage=storage,
                            owner_id=owner,
                            contact_phone=sender_identifier,
                            entities=extraction_result.entities,
                        )
                    except Exception as e:
                        print(f"[context] Error updating context with entities: {e}")

            except Exception as e:
                # Don't fail message processing if extraction fails
                if monitor_only:
                    print(f"[entity] Extraction failed for monitored message: {e}")

    if not body:
        return {"reply": None, "intent": "none", "actions": [], "session_id": session.id if session else None}

    # Se access mode é "open", responde a qualquer um; senão apenas ao owner
    if not ACCESS_MODE_OPEN and not is_owner:
        return {"reply": None, "intent": "ingest", "actions": [], "session_id": session.id if session else None}

    if should_reply is False:
        return {"reply": None, "intent": "silent", "actions": [], "session_id": session.id if session else None}

    lower = body.lower()
    session_id = session.id if session else None

    # Phase 8: Check for pending confirmations (CRM Oculto)
    # If owner has a pending confirmation, check if this message is a response
    if is_owner and session_store and owner:
        pending = session_store.get_pending_confirmation(owner)
        if pending and not pending.is_expired():
            response = _detect_confirmation_response(body)

            if response == "yes":
                # Execute the pending action
                result = _execute_pending_action(pending, storage, owner, session_id)
                session_store.clear_pending_confirmation(owner)

                # Record and return
                storage.record_interaction(sender, body, result, "confirmation_accepted")
                if session_store and session_id:
                    session_store.add_message(session_id, ContextMessage(
                        role="assistant",
                        content=result,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        metadata={"intent": "confirmation_accepted"},
                    ))

                return {
                    "reply": result,
                    "intent": "confirmation_accepted",
                    "actions": ["appointment_created"] if pending.confirmation_type == "create_appointment" else ["task_created"],
                    "session_id": session_id,
                }

            elif response == "no":
                session_store.clear_pending_confirmation(owner)
                result = "Ok, descartado."

                storage.record_interaction(sender, body, result, "confirmation_rejected")
                if session_store and session_id:
                    session_store.add_message(session_id, ContextMessage(
                        role="assistant",
                        content=result,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        metadata={"intent": "confirmation_rejected"},
                    ))

                return {
                    "reply": result,
                    "intent": "confirmation_rejected",
                    "actions": [],
                    "session_id": session_id,
                }

            # If not a clear yes/no, continue normal processing
            # but still allow the user to respond naturally

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

    # Phase 7: Check for suggestion responses
    try:
        from suggestions import SuggestionResponder, get_pending_for_owner

        pending_suggestions = get_pending_for_owner(storage, owner)
        if pending_suggestions:
            responder = SuggestionResponder(storage, _get_tool_registry())
            suggestion_response = responder.detect_response(body, pending_suggestions)

            if suggestion_response:
                # Handle the suggestion response
                tool_context = ToolContext(
                    user_phone=owner,
                    session_id=session_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    storage=storage,
                )
                result = _run_async(responder.handle_response(
                    suggestion_response,
                    pending_suggestions,
                    tool_context,
                ))

                if result and result.get("reply"):
                    storage.record_interaction(sender, body, result["reply"], "suggestion_response")
                    _record_response(session_store, session_id, result["reply"], "suggestion_response")
                    return {
                        "reply": result["reply"],
                        "intent": "suggestion_response",
                        "actions": result.get("actions", []),
                        "session_id": session_id,
                    }
    except ImportError:
        pass  # Suggestions module not installed
    except Exception as e:
        print(f"[suggestions] Response detection error: {e}")

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

    if "listar tarefas" in lower or "mostrar tarefas" in lower or "tarefas" == lower:
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

    if lower in ("agenda", "compromissos", "listar compromissos", "meus compromissos", "mostrar compromissos"):
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
        # Parse date from text first
        parsed_due = _parse_datetime(task_text)
        # Use Tool System for create_task
        result = _execute_tool(
            "create_task",
            {"title": task_text, "due_date": parsed_due},
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
            task = storage.create_task(task_text, parsed_due)
            reply = f"Tarefa criada: {task.title}"
            if parsed_due:
                reply += f" (ate {parsed_due})"
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

            # Handle successful completion with response
            if state.final_response:
                intent = state.last_tool or "agent_response"
                if state.status == AgentStatus.ERROR:
                    intent = "agent_error"
                return make_result(state.final_response, intent)

            # Handle edge case: agent finished but no response
            # Try to extract thought from last step
            for step in reversed(state.steps):
                if step.thought:
                    return make_result(step.thought, "agent_thought")

            # Last resort: inform user that processing failed
            return make_result(
                "Não consegui processar sua solicitação. Tente reformular.",
                "agent_no_response"
            )

    except Exception as e:
        print(f"[react_agent] Error: {e}")
        import traceback
        traceback.print_exc()
        # Return error message to user instead of falling through
        return make_result(
            "Ocorreu um erro ao processar. Tente novamente.",
            "agent_exception"
        )

    # Fallback for fast-path messages that weren't handled above
    return make_result("Anotado. Se quiser criar tarefas ou lembretes, me diga diretamente.", "note")
