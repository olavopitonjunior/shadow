"""
RecallMemory Tool - Semantic search in contact memories.
"""

import os
from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class RecallMemoryTool(Tool):
    """Searches memories using semantic similarity."""

    name = "recall_memory"
    description = "Busca semântica em memórias de contatos"
    category = "memory"

    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="Termo de busca (pode ser conceitual, não precisa ser exato)",
            required=True,
        ),
        ToolParameter(
            name="contact",
            type="string",
            description="Filtrar por contato (nome ou telefone, opcional)",
            required=False,
        ),
        ToolParameter(
            name="category",
            type="string",
            description="Filtrar por categoria: preference, fact, decision, entity, interaction",
            required=False,
        ),
        ToolParameter(
            name="limit",
            type="number",
            description="Número máximo de resultados (padrão: 5)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        query = params.get("query", "").strip()
        contact = params.get("contact", "").strip()
        category = params.get("category", "").strip()
        limit = params.get("limit", 5)

        if not query:
            return ToolResult.error("Termo de busca é obrigatório")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Get OpenAI key
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return ToolResult.error("OPENAI_API_KEY não configurada para busca semântica")

        try:
            from contact_memory import get_contact_memory

            memory = get_contact_memory(openai_key=openai_key)
            if not memory:
                return ToolResult.error("Sistema de memória não disponível")

            # Resolve contact phone if name provided
            contact_phone = None
            if contact:
                storage = context.storage
                if storage:
                    resolved = storage.find_contact_by_name(owner_id, contact)
                    if resolved:
                        contact_phone = resolved.get("contact_phone")
                    else:
                        contact_phone = contact  # Try as-is

            # Perform semantic search
            results = memory.recall(
                owner_id=owner_id,
                query=query,
                contact_phone=contact_phone,
                category=category if category else None,
                limit=limit,
            )

            if not results:
                return ToolResult.ok(
                    message="Nenhuma memória encontrada",
                    data={"memories": [], "count": 0, "query": query},
                    display_text=f"Nenhuma memória encontrada para '{query}'.",
                )

            # Format results
            lines = [f"🧠 Memórias ({len(results)}) para '{query}':"]

            category_emoji = {
                "preference": "⭐",
                "decision": "✅",
                "fact": "📋",
                "entity": "🏢",
                "interaction": "💬",
            }

            for i, m in enumerate(results, 1):
                emoji = category_emoji.get(m["category"], "📝")
                text = m["text"][:80]
                if len(m["text"]) > 80:
                    text += "..."
                score = f"{m['score']:.0%}"

                line = f"{i}. {emoji} {text} [{score}]"
                if m.get("contact_phone"):
                    line += f" (contato: {m['contact_phone'][-4:]})"
                lines.append(line)

            return ToolResult.ok(
                message=f"{len(results)} memórias encontradas",
                data={"memories": results, "count": len(results), "query": query},
                display_text="\n".join(lines),
            )

        except ImportError as e:
            return ToolResult.error(f"Dependência não instalada: {e}")
        except Exception as e:
            return ToolResult.error(f"Erro na busca: {str(e)}")
