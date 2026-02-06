"""
ListCategories Tool - Lists available task categories and appointment types.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ListCategoriesTool(Tool):
    """Lists available categories for tasks and appointments."""

    name = "list_categories"
    description = "Lista categorias de tarefas e tipos de compromissos disponíveis"
    category = "categories"

    parameters = [
        ToolParameter(
            name="type",
            type="string",
            description="Tipo de categoria a listar: 'task', 'appointment', ou 'all'",
            required=False,
            enum=["task", "appointment", "all"],
            default="all",
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        category_type = params.get("type", "all")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            lines = []
            data = {}

            if category_type in ("task", "all"):
                task_categories = storage.list_task_categories(owner_id)
                data["task_categories"] = task_categories

                if task_categories:
                    lines.append("📋 CATEGORIAS DE TAREFAS:")
                    for cat in task_categories:
                        default_mark = " (padrão)" if cat.get("is_default") else ""
                        lines.append(f"  • {cat['name']}{default_mark}")
                else:
                    lines.append("📋 Nenhuma categoria de tarefa encontrada")

            if category_type in ("appointment", "all"):
                if lines:
                    lines.append("")
                appointment_types = storage.list_appointment_types(owner_id)
                data["appointment_types"] = appointment_types

                if appointment_types:
                    lines.append("📅 TIPOS DE COMPROMISSO:")
                    for apt in appointment_types:
                        duration = apt.get("default_duration", 60)
                        location = apt.get("location_type", "")
                        location_emoji = {
                            "in_person": "🏢",
                            "video_call": "📹",
                            "phone_call": "📞",
                        }.get(location, "")
                        default_mark = " (padrão)" if apt.get("is_default") else ""
                        lines.append(f"  • {apt['name']} {location_emoji} ({duration}min){default_mark}")
                else:
                    lines.append("📅 Nenhum tipo de compromisso encontrado")

            # Add hint if no categories
            total = len(data.get("task_categories", [])) + len(data.get("appointment_types", []))
            if total == 0:
                lines.append("")
                lines.append("💡 Use create_category para criar categorias personalizadas")

            return ToolResult.ok(
                message="Categorias listadas com sucesso",
                data=data,
                display_text="\n".join(lines),
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao listar categorias: {str(e)}")
