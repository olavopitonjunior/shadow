"""
GetContact Tool - Retrieves detailed information about a contact.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class GetContactTool(Tool):
    """Retrieves contact information by name or phone."""

    name = "get_contact"
    description = "Busca informações detalhadas sobre um contato"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="identifier",
            type="string",
            description="Nome ou telefone do contato",
            required=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        identifier = params.get("identifier", "").strip()
        if not identifier:
            return ToolResult.error("Nome ou telefone do contato é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Try to find contact
        contact = storage.find_contact_by_name(owner_id, identifier)
        if not contact:
            # Try direct phone lookup
            contact = storage.get_contact_context(owner_id, contact_phone=identifier)

        if not contact:
            return ToolResult.ok(
                message="Contato não encontrado",
                data={"found": False, "identifier": identifier},
                display_text=f"Não encontrei informações sobre '{identifier}'.",
            )

        # Format contact info
        name = contact.get("contact_name") or contact.get("contact_phone") or identifier
        phone = contact.get("contact_phone", "N/A")
        last_interaction = contact.get("last_interaction", "N/A")
        message_count = contact.get("message_count", 0)
        interaction_count = contact.get("interaction_count", 0)
        summary = contact.get("summary") or "Sem resumo disponível"
        topics = contact.get("topics") or []
        sentiment = contact.get("sentiment") or "neutral"
        relationship = contact.get("relationship_type") or "desconhecido"

        # Get aliases
        aliases = storage.list_aliases_for_contact(owner_id, phone) if phone != "N/A" else []

        lines = [
            f"📇 {name}",
            f"Telefone: {phone}",
            f"Tipo: {relationship}",
            f"Última interação: {last_interaction[:10] if last_interaction != 'N/A' else 'N/A'}",
            f"Mensagens: {message_count} | Interações: {interaction_count}",
            "",
            f"Resumo: {summary}",
        ]

        if topics:
            lines.append(f"Tópicos: {', '.join(topics[:5])}")

        if sentiment != "neutral":
            emoji = "😊" if sentiment == "positive" else "😐"
            lines.append(f"Sentimento: {emoji} {sentiment}")

        if aliases:
            lines.append(f"Apelidos: {', '.join(aliases)}")

        return ToolResult.ok(
            message="Contato encontrado",
            data={
                "found": True,
                "contact": contact,
                "aliases": aliases,
            },
            display_text="\n".join(lines),
        )
