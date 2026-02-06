"""
StoreMemory Tool - Saves important information as memory.
"""

import os
from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class StoreMemoryTool(Tool):
    """Stores important information as semantic memory."""

    name = "store_memory"
    description = "Salva informação importante na memória de contatos"
    category = "memory"

    parameters = [
        ToolParameter(
            name="text",
            type="string",
            description="Informação a ser memorizada",
            required=True,
        ),
        ToolParameter(
            name="contact",
            type="string",
            description="Contato relacionado (nome ou telefone, opcional)",
            required=False,
        ),
        ToolParameter(
            name="category",
            type="string",
            description="Categoria: preference, fact, decision, entity, interaction (padrão: auto-detecta)",
            required=False,
        ),
        ToolParameter(
            name="importance",
            type="number",
            description="Importância de 0 a 1 (padrão: 0.7)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        text = params.get("text", "").strip()
        contact = params.get("contact", "").strip()
        category = params.get("category", "").strip()
        importance = params.get("importance", 0.7)

        if not text:
            return ToolResult.error("Texto da memória é obrigatório")

        if len(text) < 10:
            return ToolResult.error("Memória muito curta. Forneça mais detalhes.")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Validate importance
        if not isinstance(importance, (int, float)) or importance < 0 or importance > 1:
            importance = 0.7

        # Get OpenAI key
        openai_key = os.getenv("OPENAI_API_KEY")

        try:
            from contact_memory import get_contact_memory, detect_category

            # Auto-detect category if not provided
            if not category:
                category = detect_category(text)

            # Valid categories
            valid_categories = ["preference", "fact", "decision", "entity", "interaction"]
            if category not in valid_categories:
                category = "interaction"

            # Resolve contact phone if name provided
            contact_phone = None
            contact_name = None
            if contact:
                storage = context.storage
                if storage:
                    resolved = storage.find_contact_by_name(owner_id, contact)
                    if resolved:
                        contact_phone = resolved.get("contact_phone")
                        contact_name = resolved.get("contact_name") or contact
                    else:
                        contact_phone = contact if contact.startswith("+") else None
                        contact_name = contact

            # Store in LanceDB (if available)
            memory_id = None
            if openai_key:
                memory = get_contact_memory(openai_key=openai_key)
                if memory:
                    memory_id = memory.store(
                        owner_id=owner_id,
                        text=text,
                        contact_phone=contact_phone,
                        category=category,
                        importance=importance,
                    )

            # Always store in SQLite/Supabase as backup
            storage = context.storage
            if storage:
                storage.save_contact_memory(
                    owner_id=owner_id,
                    text=text,
                    contact_phone=contact_phone,
                    category=category,
                    importance=importance,
                )

            # Format response
            category_emoji = {
                "preference": "⭐",
                "decision": "✅",
                "fact": "📋",
                "entity": "🏢",
                "interaction": "💬",
            }
            emoji = category_emoji.get(category, "📝")

            lines = [f"{emoji} Memória salva ({category})"]
            lines.append(f"Texto: {text[:50]}...")
            if contact_name:
                lines.append(f"Contato: {contact_name}")
            lines.append(f"Importância: {importance:.0%}")

            return ToolResult.ok(
                message="Memória armazenada",
                data={
                    "memory_id": memory_id,
                    "text": text,
                    "category": category,
                    "importance": importance,
                    "contact_phone": contact_phone,
                },
                display_text="\n".join(lines),
            )

        except ImportError as e:
            # Fallback to SQLite only
            storage = context.storage
            if storage:
                storage.save_contact_memory(
                    owner_id=owner_id,
                    text=text,
                    contact_phone=contact if contact.startswith("+") else None,
                    category=category or "interaction",
                    importance=importance,
                )
                return ToolResult.ok(
                    message="Memória salva (backup)",
                    data={"text": text, "category": category or "interaction"},
                    display_text=f"📝 Memória salva: {text[:50]}... (modo backup)",
                )
            return ToolResult.error(f"Erro ao salvar memória: {e}")
        except Exception as e:
            return ToolResult.error(f"Erro ao salvar memória: {str(e)}")
