"""
CompleteTask Tool - Marks a task as completed.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class CompleteTaskTool(Tool):
    """Marks a task as completed."""

    name = "complete_task"
    description = "Marca uma tarefa como concluída"
    category = "tasks"

    parameters = [
        ToolParameter(
            name="task_id",
            type="integer",
            description="ID da tarefa a ser concluída",
            required=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        task_id = params.get("task_id")
        if not task_id:
            return ToolResult.error("ID da tarefa é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        try:
            task = storage.complete_task(task_id)

            if not task:
                return ToolResult.error(f"Tarefa #{task_id} não encontrada")

            return ToolResult.ok(
                message="Tarefa concluída com sucesso",
                data={
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                },
                display_text=f"✅ Tarefa concluída: {task.title}",
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao concluir tarefa: {str(e)}")
