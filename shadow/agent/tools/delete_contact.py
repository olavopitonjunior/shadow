"""
DeleteContact Tool - Deletes a contact from the CRM.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class DeleteContactTool(Tool):
    """Deletes a contact (soft delete by default, can be restored)."""

    name = "delete_contact"
    description = "Exclui um contato do CRM (pode ser restaurado depois)"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="identifier",
            type="string",
            description="Nome ou telefone do contato a excluir",
            required=True,
        ),
        ToolParameter(
            name="hard_delete",
            type="boolean",
            description="Se True, exclui permanentemente (não pode ser restaurado)",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="confirm",
            type="boolean",
            description="Confirmação da exclusão (deve ser True para executar)",
            required=False,
            default=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        identifier = params.get("identifier", "").strip()
        if not identifier:
            return ToolResult.error("Nome ou telefone do contato é obrigatório")

        hard_delete = params.get("hard_delete", False)
        confirm = params.get("confirm", False)

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # First, check if contact exists
        contact = storage.find_contact_by_name(owner_id, identifier)
        if not contact:
            contact = storage.get_contact_context(owner_id, contact_phone=identifier)

        if not contact:
            return ToolResult.ok(
                message="Contato não encontrado",
                data={"found": False, "identifier": identifier},
                display_text=f"Não encontrei o contato '{identifier}'.",
            )

        name = contact.get("contact_name") or contact.get("contact_phone") or identifier
        phone = contact.get("contact_phone", "")

        # Require confirmation for deletion
        if not confirm:
            delete_type = "permanentemente" if hard_delete else "temporariamente"
            return ToolResult.ok(
                message="Confirmação necessária",
                data={
                    "needs_confirmation": True,
                    "phone": phone,
                    "name": name,
                    "hard_delete": hard_delete,
                },
                display_text=f"Tem certeza que deseja excluir {delete_type} o contato '{name}'?\n"
                             f"Para confirmar, use: delete_contact(identifier=\"{identifier}\", confirm=True"
                             + (", hard_delete=True" if hard_delete else "") + ")",
            )

        # Execute deletion
        result = storage.delete_contact(owner_id, identifier, hard_delete=hard_delete)

        if not result.get("success"):
            return ToolResult.error(result.get("error", "Erro ao excluir contato"))

        if hard_delete:
            return ToolResult.ok(
                message="Contato excluído permanentemente",
                data=result,
                display_text=f"🗑️ Contato '{result.get('name')}' excluído permanentemente.",
            )
        else:
            return ToolResult.ok(
                message="Contato excluído",
                data=result,
                display_text=f"🗑️ Contato '{result.get('name')}' excluído.\n"
                             f"Para restaurar: restore_contact(phone=\"{result.get('phone')}\")",
            )
