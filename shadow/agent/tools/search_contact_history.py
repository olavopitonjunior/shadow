"""
SearchContactHistory Tool - Searches message history with a contact.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class SearchContactHistoryTool(Tool):
    """Searches conversation history with a specific contact."""

    name = "search_contact_history"
    description = "Busca no histórico de mensagens com um contato"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="contact",
            type="string",
            description="Nome ou telefone do contato",
            required=True,
        ),
        ToolParameter(
            name="query",
            type="string",
            description="Termo de busca (opcional - sem filtro mostra últimas mensagens)",
            required=False,
        ),
        ToolParameter(
            name="limit",
            type="number",
            description="Número máximo de mensagens (padrão: 10)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        contact = params.get("contact", "").strip()
        query = params.get("query", "").strip()
        limit = params.get("limit", 10)

        if not contact:
            return ToolResult.error("Nome ou telefone do contato é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Get messages
        messages = storage.search_conversations_with_contact(
            owner_id=owner_id,
            contact_identifier=contact,
            limit=limit * 2 if query else limit,  # Get more if filtering
        )

        if not messages:
            return ToolResult.ok(
                message="Nenhuma mensagem encontrada",
                data={"messages": [], "count": 0, "contact": contact},
                display_text=f"Nenhuma mensagem encontrada com '{contact}'.",
            )

        # Filter by query if provided
        if query:
            query_lower = query.lower()
            messages = [m for m in messages if query_lower in (m.get("content") or "").lower()]
            messages = messages[:limit]

        if not messages:
            return ToolResult.ok(
                message="Nenhuma mensagem com esse termo",
                data={"messages": [], "count": 0, "contact": contact, "query": query},
                display_text=f"Nenhuma mensagem contendo '{query}' com '{contact}'.",
            )

        # Format messages
        contact_name = messages[0].get("contact_name") or contact
        lines = [f"📜 Histórico com {contact_name} ({len(messages)} msgs):"]

        for msg in messages:
            direction = msg.get("direction", "inbound")
            content = msg.get("content", "")[:60]
            timestamp = msg.get("timestamp", "")[:10]

            sender = "Você" if direction == "outbound" else contact_name
            line = f"[{timestamp}] {sender}: {content}"
            if len(msg.get("content", "")) > 60:
                line += "..."
            lines.append(line)

        return ToolResult.ok(
            message=f"{len(messages)} mensagens encontradas",
            data={
                "messages": messages,
                "count": len(messages),
                "contact": contact,
                "query": query,
            },
            display_text="\n".join(lines),
        )
