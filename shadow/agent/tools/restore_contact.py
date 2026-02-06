"""
RestoreContact Tool - Restores a soft-deleted contact.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class RestoreContactTool(Tool):
    """Restores a previously soft-deleted contact."""

    name = "restore_contact"
    description = "Restaura um contato que foi excluido (soft delete)"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="phone",
            type="string",
            description="Telefone do contato a restaurar",
            required=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        phone = params.get("phone", "").strip()
        if not phone:
            return ToolResult.error("Telefone do contato e obrigatorio")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage nao disponivel")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuario nao identificado")

        # First, check if there are deleted contacts with this phone
        deleted = storage.list_deleted_contacts(owner_id, limit=50)
        matching = [c for c in deleted if c.get("contact_phone") == phone]

        if not matching:
            # Try to find by partial match
            matching = [c for c in deleted if phone in c.get("contact_phone", "")]

        if not matching:
            # No deleted contact found
            all_deleted = [f"- {c.get('contact_name', 'Sem nome')} ({c.get('contact_phone')})"
                          for c in deleted[:5]]
            if all_deleted:
                deleted_list = "\n".join(all_deleted)
                return ToolResult.ok(
                    message="Contato nao encontrado nos excluidos",
                    data={"found": False, "phone": phone, "deleted_count": len(deleted)},
                    display_text=f"Nao encontrei '{phone}' nos contatos excluidos.\n\n"
                                 f"Contatos excluidos recentemente:\n{deleted_list}",
                )
            else:
                return ToolResult.ok(
                    message="Nenhum contato excluido",
                    data={"found": False, "phone": phone, "deleted_count": 0},
                    display_text="Nao ha contatos excluidos para restaurar.",
                )

        # Found a match, restore it
        contact_phone = matching[0].get("contact_phone", phone)
        result = storage.restore_contact(owner_id, contact_phone)

        if not result.get("success"):
            return ToolResult.error(result.get("error", "Erro ao restaurar contato"))

        name = result.get("name", contact_phone)
        return ToolResult.ok(
            message="Contato restaurado",
            data=result,
            display_text=f"Contato '{name}' restaurado com sucesso!",
        )
