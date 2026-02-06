"""
ListContacts Tool - Lists recent contacts.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ListContactsTool(Tool):
    """Lists recent contacts with basic info."""

    name = "list_contacts"
    description = "Lista contatos recentes"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="limit",
            type="number",
            description="Número máximo de contatos (padrão: 10)",
            required=False,
        ),
        ToolParameter(
            name="filter",
            type="string",
            description="Filtro: 'all', 'recent', 'active' (padrão: recent)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        limit = params.get("limit", 10)
        filter_type = params.get("filter", "recent")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        # Get recent contacts
        contacts = storage.list_recent_contacts(limit=limit)

        if not contacts:
            return ToolResult.ok(
                message="Nenhum contato encontrado",
                data={"contacts": [], "count": 0},
                display_text="Você ainda não tem contatos registrados.",
            )

        # Format list
        lines = [f"📋 Contatos ({len(contacts)}):"]
        for i, contact in enumerate(contacts, 1):
            name = contact.get("name") or contact.get("phone_number") or contact.get("phone", "Desconhecido")
            phone = contact.get("phone_number") or contact.get("phone", "")
            last = contact.get("last_interaction_at", "")

            line = f"{i}. {name}"
            if phone and phone != name:
                line += f" ({phone[-4:]})"  # Last 4 digits
            if last:
                line += f" - {last[:10]}"

            lines.append(line)

        return ToolResult.ok(
            message=f"{len(contacts)} contatos encontrados",
            data={"contacts": contacts, "count": len(contacts)},
            display_text="\n".join(lines),
        )
