"""
MergeContacts Tool - Merges two contacts into one.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class MergeContactsTool(Tool):
    """Merges two contacts, keeping one and transferring data from the other."""

    name = "merge_contacts"
    description = "Mescla dois contatos duplicados em um só"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="target",
            type="string",
            description="Nome ou telefone do contato que será mantido",
            required=True,
        ),
        ToolParameter(
            name="source",
            type="string",
            description="Nome ou telefone do contato que será mesclado (e depois removido)",
            required=True,
        ),
        ToolParameter(
            name="confirm",
            type="boolean",
            description="Confirmação da mesclagem (deve ser True para executar)",
            required=False,
            default=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        target = params.get("target", "").strip()
        source = params.get("source", "").strip()
        confirm = params.get("confirm", False)

        if not target:
            return ToolResult.error("Contato alvo (target) é obrigatório")
        if not source:
            return ToolResult.error("Contato origem (source) é obrigatório")
        if target.lower() == source.lower():
            return ToolResult.error("Os contatos devem ser diferentes")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Find target contact
        target_contact = storage.find_contact_by_name(owner_id, target)
        if not target_contact:
            target_contact = storage.get_contact_context(owner_id, contact_phone=target)

        if not target_contact:
            return ToolResult.ok(
                message="Contato alvo não encontrado",
                data={"found": False, "target": target},
                display_text=f"Não encontrei o contato alvo '{target}'.",
            )

        # Find source contact
        source_contact = storage.find_contact_by_name(owner_id, source)
        if not source_contact:
            source_contact = storage.get_contact_context(owner_id, contact_phone=source)

        if not source_contact:
            return ToolResult.ok(
                message="Contato origem não encontrado",
                data={"found": False, "source": source},
                display_text=f"Não encontrei o contato origem '{source}'.",
            )

        target_name = target_contact.get("contact_name") or target_contact.get("contact_phone")
        target_phone = target_contact.get("contact_phone")
        source_name = source_contact.get("contact_name") or source_contact.get("contact_phone")
        source_phone = source_contact.get("contact_phone")

        # Require confirmation
        if not confirm:
            return ToolResult.ok(
                message="Confirmação necessária",
                data={
                    "needs_confirmation": True,
                    "target_phone": target_phone,
                    "target_name": target_name,
                    "source_phone": source_phone,
                    "source_name": source_name,
                },
                display_text=(
                    f"Mesclar contatos:\n"
                    f"📥 Manter: {target_name} ({target_phone})\n"
                    f"📤 Mesclar: {source_name} ({source_phone})\n\n"
                    f"O contato '{source_name}' será removido e seus dados transferidos.\n"
                    f"Para confirmar, use: merge_contacts(target=\"{target}\", source=\"{source}\", confirm=True)"
                ),
            )

        # Execute merge
        result = storage.merge_contacts(owner_id, target_phone, source_phone)

        if not result.get("success"):
            return ToolResult.error(result.get("error", "Erro ao mesclar contatos"))

        return ToolResult.ok(
            message="Contatos mesclados com sucesso",
            data=result,
            display_text=(
                f"✅ Contatos mesclados!\n"
                f"'{result.get('source_name')}' foi mesclado em '{result.get('target_name')}'.\n"
                f"Apelidos e memórias foram transferidos."
            ),
        )
