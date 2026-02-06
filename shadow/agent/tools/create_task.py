"""
CreateTask Tool - Creates a new task.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class CreateTaskTool(Tool):
    """Creates a new task in the system."""

    name = "create_task"
    description = "Cria uma nova tarefa com título e data de vencimento opcional"
    category = "tasks"

    parameters = [
        ToolParameter(
            name="title",
            type="string",
            description="Título da tarefa",
            required=True,
        ),
        ToolParameter(
            name="due_date",
            type="string",
            description="Data de vencimento (ISO 8601 ou texto como 'amanhã')",
            required=False,
        ),
        ToolParameter(
            name="priority",
            type="string",
            description="Prioridade da tarefa",
            required=False,
            enum=["low", "normal", "high", "urgent"],
            default="normal",
        ),
        ToolParameter(
            name="category",
            type="string",
            description="Categoria da tarefa (ex: 'trabalho', 'pessoal', 'compras')",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        title = params.get("title", "").strip()
        if not title:
            return ToolResult.error("Título da tarefa é obrigatório")

        due_date = params.get("due_date")
        priority = params.get("priority", "normal")
        category_name = params.get("category")

        # Parse due_date if provided
        due_at = None
        if due_date:
            due_at = self._parse_date(due_date, context)

        # Get storage from context
        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone

        try:
            # Resolve category if provided
            category_id = None
            category_display = ""
            if category_name and owner_id:
                cat = storage.get_category_by_name(owner_id, category_name, "task")
                if cat:
                    category_id = cat.get("id")
                    category_display = f" [{cat['name']}]"

            # Create task in storage (returns Task object)
            task = storage.create_task(title=title, due_at=due_at)

            # Update with category if found (after creation)
            if category_id:
                storage.update_task(task.id, category_id=category_id, priority=priority)

            return ToolResult.ok(
                message="Tarefa criada com sucesso",
                data={
                    "task_id": task.id,
                    "title": task.title,
                    "due_at": task.due_at,
                    "priority": priority,
                    "category": category_name,
                },
                display_text=f"✅ Tarefa criada: {title}{category_display}"
                + (f" (vence em {due_date})" if due_date else ""),
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao criar tarefa: {str(e)}")

    def _parse_date(self, date_str: str, context: ToolContext) -> str | None:
        """Parse date string to ISO format using dateparser."""
        import dateparser
        from datetime import datetime

        if not date_str:
            return None

        # Use dateparser for intelligent parsing
        # Handles: "amanhã", "próxima semana", "em 3 dias", "sexta-feira", etc.
        parsed = dateparser.parse(
            date_str,
            languages=['pt', 'en'],
            settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now(),
            }
        )

        if parsed:
            return parsed.isoformat()

        # Don't return raw text - return None if can't parse
        return None
