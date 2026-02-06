"""
ForgetMemory Tool - Removes memories (GDPR compliant).
"""

import os
from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ForgetMemoryTool(Tool):
    """Removes memories for GDPR compliance."""

    name = "forget_memory"
    description = "Remove memórias sobre um contato (GDPR)"
    category = "memory"

    parameters = [
        ToolParameter(
            name="contact",
            type="string",
            description="Contato cujas memórias serão removidas",
            required=True,
        ),
        ToolParameter(
            name="confirm",
            type="boolean",
            description="Confirma a remoção (necessário para executar)",
            required=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        contact = params.get("contact", "").strip()
        confirm = params.get("confirm", False)

        if not contact:
            return ToolResult.error("Contato é obrigatório")

        if not confirm:
            return ToolResult.ok(
                message="Confirmação necessária",
                data={"needs_confirmation": True, "contact": contact},
                display_text=f"⚠️ Para remover memórias sobre '{contact}', confirme a operação.",
            )

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Resolve contact phone
        storage = context.storage
        contact_phone = None
        contact_name = contact

        if storage:
            resolved = storage.find_contact_by_name(owner_id, contact)
            if resolved:
                contact_phone = resolved.get("contact_phone")
                contact_name = resolved.get("contact_name") or contact
            else:
                contact_phone = contact if contact.startswith("+") else None

        if not contact_phone:
            return ToolResult.error(f"Contato '{contact}' não encontrado")

        deleted_count = 0

        # Remove from LanceDB
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from contact_memory import get_contact_memory

                memory = get_contact_memory(openai_key=openai_key)
                if memory:
                    deleted_count = memory.forget_contact(owner_id, contact_phone)
            except Exception:
                pass

        # Also remove from SQLite/Supabase backup
        if storage:
            try:
                # SQLite version
                if hasattr(storage, '_conn'):
                    cur = storage._conn.cursor()
                    cur.execute(
                        "DELETE FROM shadow_contact_memories WHERE owner_id = ? AND contact_phone = ?",
                        (owner_id, contact_phone),
                    )
                    deleted_count = max(deleted_count, cur.rowcount)
                    storage._conn.commit()
                else:
                    # Supabase version
                    storage.client.table("shadow_contact_memories").delete().eq(
                        "owner_id", owner_id
                    ).eq("contact_phone", contact_phone).execute()
            except Exception:
                pass

        if deleted_count > 0:
            return ToolResult.ok(
                message=f"{deleted_count} memórias removidas",
                data={"deleted": deleted_count, "contact": contact_name},
                display_text=f"🗑️ {deleted_count} memórias sobre '{contact_name}' foram removidas.",
            )
        else:
            return ToolResult.ok(
                message="Nenhuma memória encontrada",
                data={"deleted": 0, "contact": contact_name},
                display_text=f"Nenhuma memória encontrada sobre '{contact_name}'.",
            )
