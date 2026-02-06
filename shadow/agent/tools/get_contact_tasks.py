"""
GetContactTasks Tool - Lists tasks related to a contact.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class GetContactTasksTool(Tool):
    """Lists tasks associated with a specific contact."""

    name = "get_contact_tasks"
    description = "Lista tarefas relacionadas a um contato"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="contact",
            type="string",
            description="Nome ou telefone do contato",
            required=True,
        ),
        ToolParameter(
            name="status",
            type="string",
            description="Filtro de status: pending, completed, all (padrão: pending)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        contact = params.get("contact", "").strip()
        status_filter = params.get("status", "pending").strip()

        if not contact:
            return ToolResult.error("Nome ou telefone do contato é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Get tasks for contact
        tasks = storage.list_tasks_for_contact(owner_id, contact)

        if not tasks:
            return ToolResult.ok(
                message="Nenhuma tarefa encontrada",
                data={"tasks": [], "count": 0, "contact": contact},
                display_text=f"Nenhuma tarefa relacionada a '{contact}'.",
            )

        # Filter by status
        if status_filter == "pending":
            tasks = [t for t in tasks if t.get("status") in ("pending", "extracted")]
        elif status_filter == "completed":
            tasks = [t for t in tasks if t.get("status") == "completed"]
        # "all" shows everything

        if not tasks:
            return ToolResult.ok(
                message="Nenhuma tarefa com esse status",
                data={"tasks": [], "count": 0, "contact": contact, "status": status_filter},
                display_text=f"Nenhuma tarefa '{status_filter}' relacionada a '{contact}'.",
            )

        # Format tasks
        lines = [f"📋 Tarefas com {contact} ({len(tasks)}):"]

        for i, task in enumerate(tasks, 1):
            title = task.get("title", "Sem título")
            due = task.get("due_at") or task.get("due_date") or ""
            status = task.get("status", "pending")
            relation = task.get("relation_type", "")

            # Status emoji
            status_emoji = {
                "pending": "⏳",
                "completed": "✅",
                "extracted": "📥",
            }.get(status, "❓")

            line = f"{i}. {status_emoji} {title}"

            if due:
                due_display = due[:10] if "T" in due else due
                line += f" (até {due_display})"

            if relation:
                relation_display = {
                    "requester": "solicitante",
                    "assigned": "responsável",
                    "mentioned": "mencionado",
                }.get(relation, relation)
                line += f" [{relation_display}]"

            lines.append(line)

        return ToolResult.ok(
            message=f"{len(tasks)} tarefas encontradas",
            data={
                "tasks": tasks,
                "count": len(tasks),
                "contact": contact,
                "status": status_filter,
            },
            display_text="\n".join(lines),
        )
