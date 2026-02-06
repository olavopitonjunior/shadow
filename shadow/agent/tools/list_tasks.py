"""
ListTasks Tool - Lists pending tasks.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ListTasksTool(Tool):
    """Lists tasks from the system."""

    name = "list_tasks"
    description = "Lista tarefas pendentes ou filtradas por status"
    category = "tasks"

    parameters = [
        ToolParameter(
            name="status",
            type="string",
            description="Filtrar por status",
            required=False,
            enum=["pending", "done", "cancelled", "all"],
            default="pending",
        ),
        ToolParameter(
            name="limit",
            type="number",
            description="Número máximo de tarefas a retornar",
            required=False,
            default=10,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        status = params.get("status", "pending")
        limit = int(params.get("limit", 10))

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        try:
            # Get tasks from storage (currently only lists pending tasks)
            tasks = storage.list_tasks(limit=limit)

            if not tasks:
                return ToolResult.ok(
                    message="Nenhuma tarefa encontrada",
                    data={"tasks": [], "count": 0},
                    display_text="📋 Você não tem tarefas pendentes.",
                )

            # Format for display
            task_list = []
            for task in tasks:
                task_dict = {
                    "id": task.id,
                    "title": task.title,
                    "due_at": task.due_at,
                    "status": task.status,
                }
                task_list.append(task_dict)

            # Build display text
            lines = ["📋 Suas tarefas:"]
            for i, task in enumerate(task_list, 1):
                status_icon = "⬜" if task["status"] == "pending" else "✅"
                due = f" (vence: {task['due_at']})" if task.get("due_at") else ""
                lines.append(f"{i}. {status_icon} {task['title']}{due}")

            return ToolResult.ok(
                message=f"Encontradas {len(task_list)} tarefas",
                data={"tasks": task_list, "count": len(task_list)},
                display_text="\n".join(lines),
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao listar tarefas: {str(e)}")
