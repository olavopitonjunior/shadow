"""
UpdateTask Tool - Updates an existing task.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class UpdateTaskTool(Tool):
    """Updates an existing task in the system."""

    name = "update_task"
    description = "Atualiza uma tarefa existente (título, data ou status)"
    category = "tasks"

    parameters = [
        ToolParameter(
            name="task_id",
            type="integer",
            description="ID da tarefa a ser atualizada",
            required=True,
        ),
        ToolParameter(
            name="title",
            type="string",
            description="Novo título da tarefa",
            required=False,
        ),
        ToolParameter(
            name="due_date",
            type="string",
            description="Nova data de vencimento (ISO 8601 ou texto como 'amanhã')",
            required=False,
        ),
        ToolParameter(
            name="status",
            type="string",
            description="Novo status da tarefa",
            required=False,
            enum=["pending", "in_progress", "completed", "cancelled"],
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        task_id = params.get("task_id")
        if not task_id:
            return ToolResult.error("ID da tarefa é obrigatório")

        title = params.get("title")
        due_date = params.get("due_date")
        status = params.get("status")

        # At least one field must be provided
        if title is None and due_date is None and status is None:
            return ToolResult.error("Pelo menos um campo deve ser fornecido para atualização")

        # Parse due_date if provided
        due_at = None
        if due_date:
            due_at = self._parse_date(due_date, context)

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        try:
            task = storage.update_task(
                task_id=task_id,
                title=title,
                due_at=due_at,
                status=status,
            )

            if not task:
                return ToolResult.error(f"Tarefa #{task_id} não encontrada")

            # Build update description
            updates = []
            if title:
                updates.append(f"título: {title}")
            if due_date:
                updates.append(f"vencimento: {due_date}")
            if status:
                updates.append(f"status: {status}")

            return ToolResult.ok(
                message="Tarefa atualizada com sucesso",
                data={
                    "task_id": task.id,
                    "title": task.title,
                    "due_at": task.due_at,
                    "status": task.status,
                },
                display_text=f"✅ Tarefa #{task_id} atualizada: {', '.join(updates)}",
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao atualizar tarefa: {str(e)}")

    def _parse_date(self, date_str: str, context: ToolContext) -> str | None:
        """Parse date string to ISO format using dateparser."""
        import dateparser
        from datetime import datetime

        if not date_str:
            return None

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
        return None
