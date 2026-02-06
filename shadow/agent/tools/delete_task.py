"""
DeleteTask Tool - Deletes a task.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class DeleteTaskTool(Tool):
    """Deletes a task from the system."""

    name = "delete_task"
    description = "Exclui uma tarefa (pode ser restaurada a menos que hard_delete=true)"
    category = "tasks"

    parameters = [
        ToolParameter(
            name="task_id",
            type="integer",
            description="ID da tarefa a ser excluída",
            required=True,
        ),
        ToolParameter(
            name="hard_delete",
            type="boolean",
            description="Se true, exclui permanentemente (não pode ser restaurada)",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="confirm",
            type="boolean",
            description="Confirmação obrigatória para exclusão",
            required=False,
            default=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        task_id = params.get("task_id")
        if not task_id:
            return ToolResult.error("ID da tarefa é obrigatório")

        hard_delete = params.get("hard_delete", False)
        confirm = params.get("confirm", False)

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        # Get task first to show details
        task = storage.get_task(task_id)
        if not task:
            return ToolResult.error(f"Tarefa #{task_id} não encontrada")

        # Require confirmation for deletion
        if not confirm:
            action = "PERMANENTEMENTE" if hard_delete else "excluir"
            return ToolResult.ok(
                message="Confirmação necessária",
                data={"needs_confirmation": True, "task_id": task_id, "title": task.title},
                display_text=f"⚠️ Deseja {action} a tarefa '{task.title}'?\n"
                f"Use confirm=true para confirmar.",
            )

        try:
            result = storage.delete_task(task_id, hard_delete=hard_delete)

            if not result.get("success"):
                return ToolResult.error(result.get("error", "Erro desconhecido"))

            action = "excluída permanentemente" if hard_delete else "excluída"
            return ToolResult.ok(
                message=f"Tarefa {action} com sucesso",
                data=result,
                display_text=f"🗑️ Tarefa '{result['title']}' {action}",
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao excluir tarefa: {str(e)}")
