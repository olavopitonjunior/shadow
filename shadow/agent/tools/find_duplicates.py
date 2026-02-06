"""
FindDuplicates Tool - Finds potential duplicate contacts.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class FindDuplicatesTool(Tool):
    """Finds contacts that might be duplicates based on name similarity."""

    name = "find_duplicates"
    description = "Encontra contatos que podem ser duplicados"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="threshold",
            type="number",
            description="Similaridade mínima (0.0 a 1.0, padrão 0.7)",
            required=False,
            default=0.7,
        ),
        ToolParameter(
            name="limit",
            type="number",
            description="Número máximo de duplicatas a retornar",
            required=False,
            default=10,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        threshold = float(params.get("threshold", 0.7))
        limit = int(params.get("limit", 10))

        # Validate threshold
        if threshold < 0.0 or threshold > 1.0:
            return ToolResult.error("Threshold deve ser entre 0.0 e 1.0")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Find duplicates
        duplicates = storage.find_duplicate_contacts(owner_id, threshold=threshold, limit=limit)

        if not duplicates:
            return ToolResult.ok(
                message="Nenhuma duplicata encontrada",
                data={"duplicates": [], "count": 0},
                display_text="✅ Nenhum contato duplicado encontrado.",
            )

        # Format output with match types
        lines = [f"🔍 Encontrei {len(duplicates)} possível(is) duplicata(s):", ""]

        type_labels = {
            "email_match": "📧 Email idêntico",
            "name_same_ddd": "📍 Nome similar + mesmo DDD",
            "name_similar": "👤 Nome similar",
        }

        for i, dup in enumerate(duplicates, 1):
            similarity_pct = int(dup["similarity"] * 100)
            match_type = dup.get("type", "name_similar")
            type_label = type_labels.get(match_type, "Similaridade")

            name_a = dup.get("name_a") or dup["phone_a"]
            name_b = dup.get("name_b") or dup["phone_b"]

            lines.append(f"{i}. {name_a} ↔ {name_b}")
            lines.append(f"   {type_label} ({similarity_pct}%)")
            lines.append(f"   Tel: {dup['phone_a']} | {dup['phone_b']}")

            # Show emails if email match
            if match_type == "email_match" and dup.get("email_a"):
                lines.append(f"   Email: {dup['email_a']}")

        lines.append("")
        lines.append("Para mesclar, use: merge_contacts(target=\"nome1\", source=\"nome2\")")

        return ToolResult.ok(
            message=f"Encontradas {len(duplicates)} possíveis duplicatas",
            data={
                "duplicates": duplicates,
                "count": len(duplicates),
                "threshold": threshold,
            },
            display_text="\n".join(lines),
        )
