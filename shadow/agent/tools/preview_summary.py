"""
PreviewSummary Tool - Shows what today's summary would look like.
"""

from typing import Any
from datetime import datetime, date

from .base import Tool, ToolContext, ToolParameter, ToolResult


class PreviewSummaryTool(Tool):
    """Generates a preview of what the daily summary would look like."""

    name = "preview_summary"
    description = "Mostra como seria o resumo de hoje (preview)"
    category = "alerts"

    parameters = [
        ToolParameter(
            name="include_tasks",
            type="boolean",
            description="Incluir tarefas (default: true)",
            required=False,
            default=True,
        ),
        ToolParameter(
            name="include_appointments",
            type="boolean",
            description="Incluir compromissos (default: true)",
            required=False,
            default=True,
        ),
        ToolParameter(
            name="include_overdue",
            type="boolean",
            description="Incluir tarefas atrasadas (default: true)",
            required=False,
            default=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        include_tasks = params.get("include_tasks", True)
        include_appointments = params.get("include_appointments", True)
        include_overdue = params.get("include_overdue", True)

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            # Get user settings for greeting
            settings = storage.get_user_settings(owner_id)
            use_emojis = settings.get("use_emojis", True)

            # Build summary
            lines = []

            # Greeting based on time of day
            hour = datetime.now().hour
            if hour < 12:
                greeting = "☀️ Bom dia!" if use_emojis else "Bom dia!"
            elif hour < 18:
                greeting = "🌤️ Boa tarde!" if use_emojis else "Boa tarde!"
            else:
                greeting = "🌙 Boa noite!" if use_emojis else "Boa noite!"

            lines.append(greeting)
            lines.append("Aqui está seu resumo de hoje:")
            lines.append("")

            today = date.today().isoformat()
            has_content = False

            # Tasks
            if include_tasks:
                tasks = storage.list_tasks(limit=20)
                pending_tasks = [t for t in tasks if t.status == "pending"]

                if pending_tasks:
                    has_content = True
                    emoji = "📋 " if use_emojis else ""
                    lines.append(f"{emoji}*TAREFAS* ({len(pending_tasks)})")

                    # Separate by due date
                    today_tasks = []
                    overdue_tasks = []
                    future_tasks = []

                    for task in pending_tasks:
                        if task.due_at:
                            due_date = task.due_at[:10] if isinstance(task.due_at, str) else task.due_at.isoformat()[:10]
                            if due_date < today:
                                overdue_tasks.append(task)
                            elif due_date == today:
                                today_tasks.append(task)
                            else:
                                future_tasks.append(task)
                        else:
                            future_tasks.append(task)

                    if include_overdue and overdue_tasks:
                        lines.append("⚠️ Atrasadas:")
                        for task in overdue_tasks[:5]:
                            lines.append(f"  • {task.title}")

                    if today_tasks:
                        lines.append("Hoje:")
                        for task in today_tasks[:5]:
                            lines.append(f"  • {task.title}")

                    if future_tasks and not today_tasks and not overdue_tasks:
                        lines.append("Pendentes:")
                        for task in future_tasks[:5]:
                            lines.append(f"  • {task.title}")

                    lines.append("")

            # Appointments
            if include_appointments:
                appointments = storage.list_appointments(limit=10)
                # Filter to today's appointments
                today_appointments = []
                for apt in appointments:
                    if apt.scheduled_at:
                        apt_date = apt.scheduled_at[:10] if isinstance(apt.scheduled_at, str) else apt.scheduled_at.isoformat()[:10]
                        if apt_date == today:
                            today_appointments.append(apt)

                if today_appointments:
                    has_content = True
                    emoji = "📅 " if use_emojis else ""
                    lines.append(f"{emoji}*AGENDA* ({len(today_appointments)})")

                    for apt in today_appointments:
                        time_str = apt.scheduled_at[11:16] if isinstance(apt.scheduled_at, str) else apt.scheduled_at.strftime("%H:%M")
                        lines.append(f"  • {time_str} - {apt.title}")

                    lines.append("")

            # Closing
            if has_content:
                closing = "Tenha um ótimo dia! 🚀" if use_emojis else "Tenha um ótimo dia!"
                lines.append(closing)
            else:
                lines.append("Nada programado para hoje! 🎉" if use_emojis else "Nada programado para hoje!")

            display_text = "\n".join(lines)

            return ToolResult.ok(
                message="Preview do resumo gerado",
                data={
                    "preview": display_text,
                    "has_content": has_content,
                },
                display_text=display_text,
            )

        except Exception as e:
            return ToolResult.error(f"Erro ao gerar preview: {str(e)}")
