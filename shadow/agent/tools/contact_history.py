"""
ContactHistory Tool - Shows complete interaction history with a contact.

Phase 8E: CRM Oculto - Histórico completo de interações.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ContactHistoryTool(Tool):
    """Shows complete history of interactions with a contact."""

    name = "contact_history"
    description = "Mostra histórico completo de interações com um contato (tarefas, compromissos, mensagens, memórias)"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="contact_name",
            type="string",
            description="Nome do contato",
            required=True,
        ),
        ToolParameter(
            name="include_messages",
            type="boolean",
            description="Incluir mensagens recentes (padrão: true)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        contact_name = params.get("contact_name", "").strip()
        include_messages = params.get("include_messages", True)

        if not contact_name:
            return ToolResult.error("Nome do contato é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Find contact
        contact = storage.find_contact_by_name(owner_id, contact_name)
        if not contact:
            contact = storage.get_contact_context(owner_id, contact_phone=contact_name)

        if not contact:
            return ToolResult.ok(
                message="Contato não encontrado",
                data={"found": False},
                display_text=f"Não encontrei o contato '{contact_name}'.",
            )

        contact_phone = contact.get("contact_phone")
        contact_display = contact.get("contact_name") or contact_name

        # Build timeline
        timeline = []

        # 1. Get tasks related to contact
        try:
            tasks = storage.list_tasks_for_contact(owner_id, contact_phone or contact_name)
            for task in tasks[:5]:
                timeline.append({
                    "type": "task",
                    "date": task.get("due_at") or task.get("created_at") or "",
                    "title": task.get("title", ""),
                    "status": task.get("status", "pending"),
                })
        except Exception:
            pass

        # 2. Get appointments (if contact is participant)
        try:
            appointments = storage.list_appointments(limit=20)
            for appt in appointments:
                # Check if contact is mentioned in appointment
                if contact_display.lower() in appt.title.lower() or contact_phone in str(appt):
                    timeline.append({
                        "type": "appointment",
                        "date": appt.scheduled_at or "",
                        "title": appt.title,
                        "status": "scheduled",
                    })
        except Exception:
            pass

        # 3. Get recent messages
        messages = []
        if include_messages:
            try:
                raw_messages = storage.search_conversations_with_contact(
                    owner_id, contact_phone or contact_name, limit=10
                )
                for msg in raw_messages[:5]:
                    messages.append({
                        "direction": msg.get("direction", "unknown"),
                        "content": msg.get("content", "")[:100],
                        "timestamp": msg.get("timestamp", ""),
                    })
            except Exception:
                pass

        # 4. Get aliases
        aliases = []
        if contact_phone:
            try:
                aliases = storage.list_aliases_for_contact(owner_id, contact_phone)
            except Exception:
                pass

        # 5. Get memories (if available)
        memories = []
        try:
            mem_results = storage.list_contact_memories(owner_id, contact_phone or contact_name, limit=5)
            for mem in mem_results:
                memories.append({
                    "text": mem.get("text", "")[:80],
                    "category": mem.get("category", "fact"),
                })
        except Exception:
            pass

        # Format output
        lines = [f"📋 *Histórico com {contact_display}*", ""]

        # Contact info
        if contact_phone:
            lines.append(f"📱 {contact_phone}")
        if aliases:
            lines.append(f"📝 Apelidos: {', '.join(aliases)}")
        lines.append("")

        # Summary stats
        interaction_count = contact.get("interaction_count", 0)
        message_count = contact.get("message_count", 0)
        lines.append(f"📊 {interaction_count} interações | {message_count} mensagens")
        lines.append("")

        # Tasks
        tasks_in_timeline = [t for t in timeline if t["type"] == "task"]
        if tasks_in_timeline:
            lines.append("*Tarefas:*")
            for task in tasks_in_timeline[:3]:
                status_icon = "✅" if task["status"] == "completed" else "⏳"
                lines.append(f"  {status_icon} {task['title'][:40]}")
            lines.append("")

        # Appointments
        appts_in_timeline = [t for t in timeline if t["type"] == "appointment"]
        if appts_in_timeline:
            lines.append("*Compromissos:*")
            for appt in appts_in_timeline[:3]:
                lines.append(f"  📅 {appt['title'][:40]} ({appt['date'][:10]})")
            lines.append("")

        # Memories
        if memories:
            lines.append("*Memórias:*")
            for mem in memories[:3]:
                lines.append(f"  💭 {mem['text']}")
            lines.append("")

        # Recent messages
        if messages:
            lines.append("*Mensagens recentes:*")
            for msg in messages[:3]:
                direction = "→" if msg["direction"] == "outbound" else "←"
                lines.append(f"  {direction} {msg['content'][:50]}...")
            lines.append("")

        # Summary from context
        summary = contact.get("summary")
        if summary:
            lines.append(f"*Resumo:* {summary[:150]}...")

        return ToolResult.ok(
            message="Histórico encontrado",
            data={
                "found": True,
                "contact": contact,
                "timeline": timeline,
                "messages": messages,
                "memories": memories,
                "aliases": aliases,
            },
            display_text="\n".join(lines),
        )
