"""
UpdateContact Tool - Updates an existing contact's information.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class UpdateContactTool(Tool):
    """Updates contact details."""

    name = "update_contact"
    description = "Atualiza informações de um contato existente"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="identifier",
            type="string",
            description="Nome ou telefone do contato a atualizar",
            required=True,
        ),
        ToolParameter(
            name="name",
            type="string",
            description="Novo nome (opcional)",
            required=False,
        ),
        ToolParameter(
            name="relationship",
            type="string",
            description="Tipo: client, colleague, supplier, friend, family, other",
            required=False,
        ),
        ToolParameter(
            name="notes",
            type="string",
            description="Notas sobre o contato (opcional)",
            required=False,
        ),
        ToolParameter(
            name="add_alias",
            type="string",
            description="Adicionar apelido (opcional)",
            required=False,
        ),
        ToolParameter(
            name="remove_alias",
            type="string",
            description="Remover apelido (opcional)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        identifier = params.get("identifier", "").strip()
        new_name = params.get("name", "").strip()
        relationship = params.get("relationship", "").strip()
        notes = params.get("notes", "").strip()
        add_alias = params.get("add_alias", "").strip()
        remove_alias = params.get("remove_alias", "").strip()

        if not identifier:
            return ToolResult.error("Nome ou telefone do contato é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Find the contact
        contact = storage.find_contact_by_name(owner_id, identifier)
        if not contact:
            contact = storage.get_contact_context(owner_id, contact_phone=identifier)

        if not contact:
            return ToolResult.ok(
                message="Contato não encontrado",
                data={"found": False, "identifier": identifier},
                display_text=f"Não encontrei o contato '{identifier}'.",
            )

        contact_phone = contact.get("contact_phone")
        current_name = contact.get("contact_name") or identifier
        updates = []

        # Update name
        if new_name and new_name != current_name:
            storage.update_contact_context(owner_id, contact_phone, contact_name=new_name)
            storage.upsert_contact(contact_phone, new_name)
            updates.append(f"Nome: {new_name}")

        # Update relationship type
        if relationship:
            try:
                if hasattr(storage, '_conn'):  # SQLite
                    cur = storage._conn.cursor()
                    cur.execute(
                        "UPDATE shadow_contact_context SET relationship_type = ? WHERE owner_id = ? AND contact_phone = ?",
                        (relationship, owner_id, contact_phone),
                    )
                    storage._conn.commit()
                else:  # Supabase
                    storage.client.table("shadow_contact_context").update({
                        "relationship_type": relationship,
                    }).eq("owner_id", owner_id).eq("contact_phone", contact_phone).execute()
                updates.append(f"Tipo: {relationship}")
            except Exception:
                pass

        # Update notes
        if notes:
            try:
                if hasattr(storage, '_conn'):  # SQLite
                    cur = storage._conn.cursor()
                    cur.execute(
                        "UPDATE contacts SET notes = ? WHERE phone = ?",
                        (notes, contact_phone),
                    )
                    storage._conn.commit()
                else:  # Supabase
                    storage.client.table("shadow_contacts").update({
                        "notes": notes,
                    }).eq("phone_number", contact_phone).execute()
                updates.append(f"Notas: {notes[:30]}...")
            except Exception:
                pass

        # Add alias
        if add_alias:
            if storage.add_contact_alias(owner_id, contact_phone, add_alias):
                updates.append(f"Apelido adicionado: {add_alias}")
            else:
                updates.append(f"Apelido '{add_alias}' já existe")

        # Remove alias
        if remove_alias:
            if storage.remove_contact_alias(owner_id, remove_alias):
                updates.append(f"Apelido removido: {remove_alias}")

        if not updates:
            return ToolResult.ok(
                message="Nenhuma alteração realizada",
                data={"contact_phone": contact_phone, "updates": []},
                display_text="Nenhuma alteração foi especificada.",
            )

        display_name = new_name or current_name
        lines = [f"✅ Contato {display_name} atualizado:"] + updates

        return ToolResult.ok(
            message="Contato atualizado",
            data={"contact_phone": contact_phone, "updates": updates},
            display_text="\n".join(lines),
        )
