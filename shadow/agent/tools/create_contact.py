"""
CreateContact Tool - Creates a new contact manually.
"""

import re
from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class CreateContactTool(Tool):
    """Creates a new contact with optional details."""

    name = "create_contact"
    description = "Cria um novo contato manualmente"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="phone",
            type="string",
            description="Telefone do contato (formato E164 ou com DDD)",
            required=True,
        ),
        ToolParameter(
            name="name",
            type="string",
            description="Nome do contato",
            required=True,
        ),
        ToolParameter(
            name="company",
            type="string",
            description="Empresa ou organização (opcional)",
            required=False,
        ),
        ToolParameter(
            name="relationship",
            type="string",
            description="Tipo: client, colleague, supplier, friend, family, other",
            required=False,
        ),
        ToolParameter(
            name="alias",
            type="string",
            description="Apelido para referência rápida (opcional)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        phone = params.get("phone", "").strip()
        name = params.get("name", "").strip()
        company = params.get("company", "").strip()
        relationship = params.get("relationship", "other").strip()
        alias = params.get("alias", "").strip()

        if not phone:
            return ToolResult.error("Telefone é obrigatório")

        if not name:
            return ToolResult.error("Nome é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Normalize phone number
        normalized_phone = self._normalize_phone(phone)
        if not normalized_phone:
            return ToolResult.error("Telefone inválido. Use formato com DDD (ex: 11999998888)")

        # Check if contact already exists
        existing = storage.get_contact_context(owner_id, contact_phone=normalized_phone)
        if existing:
            return ToolResult.ok(
                message="Contato já existe",
                data={"exists": True, "phone": normalized_phone},
                display_text=f"Contato {name} ({normalized_phone}) já existe no sistema.",
            )

        # Create contact in contacts table
        storage.upsert_contact(normalized_phone, name)

        # Create contact context with additional info
        storage.update_contact_context(
            owner_id=owner_id,
            contact_phone=normalized_phone,
            contact_name=name,
        )

        # Update relationship type if provided
        if relationship:
            try:
                # Use direct SQL for SQLite or Supabase update
                if hasattr(storage, '_conn'):  # SQLite
                    cur = storage._conn.cursor()
                    cur.execute(
                        "UPDATE shadow_contact_context SET relationship_type = ? WHERE owner_id = ? AND contact_phone = ?",
                        (relationship, owner_id, normalized_phone),
                    )
                    storage._conn.commit()
                else:  # Supabase
                    storage.client.table("shadow_contact_context").update({
                        "relationship_type": relationship,
                    }).eq("owner_id", owner_id).eq("contact_phone", normalized_phone).execute()
            except Exception:
                pass  # Non-critical

        # Add alias if provided
        if alias:
            storage.add_contact_alias(owner_id, normalized_phone, alias)

        lines = [
            f"✅ Contato criado: {name}",
            f"Telefone: {normalized_phone}",
        ]
        if company:
            lines.append(f"Empresa: {company}")
        if relationship and relationship != "other":
            lines.append(f"Tipo: {relationship}")
        if alias:
            lines.append(f"Apelido: {alias}")

        return ToolResult.ok(
            message="Contato criado",
            data={
                "phone": normalized_phone,
                "name": name,
                "company": company,
                "relationship": relationship,
                "alias": alias,
            },
            display_text="\n".join(lines),
        )

    def _normalize_phone(self, phone: str) -> str | None:
        """Normalize phone to E164 format."""
        # Remove non-digits
        digits = re.sub(r"\D", "", phone)

        if len(digits) < 10:
            return None

        # Add Brazil code if not present
        if not digits.startswith("55") and len(digits) <= 11:
            digits = "55" + digits

        if len(digits) < 12 or len(digits) > 13:
            return None

        return f"+{digits}"
