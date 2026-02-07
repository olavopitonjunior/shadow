"""
ListSuggestions Tool - Lists pending proactive suggestions.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ListSuggestionsTool(Tool):
    """Lists pending suggestions from the proactive suggestion system."""

    name = "list_suggestions"
    description = "Lista sugestões proativas pendentes (tarefas, compromissos, contatos detectados automaticamente)"
    category = "suggestions"

    parameters = [
        ToolParameter(
            name="status",
            type="string",
            description="Filtrar por status",
            required=False,
            enum=["pending", "sent", "all"],
            default="pending",
        ),
        ToolParameter(
            name="limit",
            type="number",
            description="Número máximo de sugestões a retornar",
            required=False,
            default=10,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        status = params.get("status", "pending")
        limit = int(params.get("limit", 10))

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            # Get suggestions based on status
            if status == "all":
                pending = storage.get_pending_suggestions(owner_id, limit=limit)
                sent = storage.get_sent_suggestions(owner_id, limit=limit)
                suggestions = pending + sent
            elif status == "sent":
                suggestions = storage.get_sent_suggestions(owner_id, limit=limit)
            else:
                suggestions = storage.get_pending_suggestions(owner_id, limit=limit)

            if not suggestions:
                return ToolResult.ok(
                    message="Nenhuma sugestão encontrada",
                    data={"suggestions": [], "count": 0},
                    display_text="💡 Nenhuma sugestão pendente no momento.",
                )

            # Format for display
            type_emoji = {
                "create_task": "📋",
                "create_appointment": "📅",
                "create_contact": "👤",
                "update_contact": "✏️",
                "conversation_summary": "📝",
            }

            lines = [f"💡 Sugestões pendentes ({len(suggestions)}):"]
            suggestion_list = []

            for i, s in enumerate(suggestions, 1):
                suggestion_dict = {
                    "id": s.get("id"),
                    "type": s.get("suggestion_type"),
                    "title": s.get("title"),
                    "confidence": s.get("confidence", 0.5),
                    "status": s.get("status"),
                }
                suggestion_list.append(suggestion_dict)

                emoji = type_emoji.get(s.get("suggestion_type"), "💡")
                confidence = int(s.get("confidence", 0.5) * 100)
                title = s.get("title", "")[:40]
                if len(s.get("title", "")) > 40:
                    title += "..."

                lines.append(f"{i}. {emoji} {title} ({confidence}%)")

            return ToolResult.ok(
                message=f"Encontradas {len(suggestion_list)} sugestões",
                data={"suggestions": suggestion_list, "count": len(suggestion_list)},
                display_text="\n".join(lines),
            )

        except Exception as e:
            return ToolResult.error(f"Erro ao listar sugestões: {str(e)}")
