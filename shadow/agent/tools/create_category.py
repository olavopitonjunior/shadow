"""
CreateCategory Tool - Creates a new task category or appointment type.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class CreateCategoryTool(Tool):
    """Creates a new category for tasks or appointments."""

    name = "create_category"
    description = "Cria uma nova categoria de tarefa ou tipo de compromisso"
    category = "categories"

    parameters = [
        ToolParameter(
            name="name",
            type="string",
            description="Nome da categoria (ex: 'projeto_x', 'cliente_y')",
            required=True,
        ),
        ToolParameter(
            name="type",
            type="string",
            description="Tipo: 'task' para categoria de tarefa, 'appointment' para tipo de compromisso",
            required=True,
            enum=["task", "appointment"],
        ),
        ToolParameter(
            name="color",
            type="string",
            description="Cor em hexadecimal (ex: '#FF5733')",
            required=False,
            default="#3B82F6",
        ),
        ToolParameter(
            name="duration",
            type="integer",
            description="Duração padrão em minutos (apenas para tipos de compromisso)",
            required=False,
            default=60,
        ),
        ToolParameter(
            name="location_type",
            type="string",
            description="Tipo de local (apenas para compromissos)",
            required=False,
            enum=["in_person", "video_call", "phone_call", "other"],
            default="other",
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        name = params.get("name", "").strip()
        if not name:
            return ToolResult.error("Nome da categoria é obrigatório")

        category_type = params.get("type")
        if not category_type:
            return ToolResult.error("Tipo (task ou appointment) é obrigatório")

        color = params.get("color", "#3B82F6")
        duration = params.get("duration", 60)
        location_type = params.get("location_type", "other")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            if category_type == "task":
                result = storage.create_task_category(
                    owner_id=owner_id,
                    name=name,
                    color=color,
                )
                if result.get("success"):
                    return ToolResult.ok(
                        message="Categoria de tarefa criada",
                        data=result,
                        display_text=f"✅ Categoria de tarefa '{name}' criada com sucesso",
                    )
                else:
                    return ToolResult.error(result.get("error", "Erro desconhecido"))

            else:  # appointment
                result = storage.create_appointment_type(
                    owner_id=owner_id,
                    name=name,
                    default_duration=duration,
                    location_type=location_type,
                    color=color,
                )
                if result.get("success"):
                    location_emoji = {
                        "in_person": "🏢",
                        "video_call": "📹",
                        "phone_call": "📞",
                    }.get(location_type, "")
                    return ToolResult.ok(
                        message="Tipo de compromisso criado",
                        data=result,
                        display_text=f"✅ Tipo de compromisso '{name}' {location_emoji} ({duration}min) criado",
                    )
                else:
                    return ToolResult.error(result.get("error", "Erro desconhecido"))

        except Exception as e:
            return ToolResult.error(f"Erro ao criar categoria: {str(e)}")
