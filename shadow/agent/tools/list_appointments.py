"""
ListAppointments Tool - Lists upcoming appointments.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ListAppointmentsTool(Tool):
    """Lists appointments from the calendar."""

    name = "list_appointments"
    description = "Lista compromissos agendados"
    category = "calendar"

    parameters = [
        ToolParameter(
            name="days",
            type="number",
            description="Número de dias a frente para listar",
            required=False,
            default=7,
        ),
        ToolParameter(
            name="limit",
            type="number",
            description="Número máximo de compromissos",
            required=False,
            default=10,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        days = int(params.get("days", 7))
        limit = int(params.get("limit", 10))

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        try:
            appointments = storage.list_appointments(limit=limit)

            if not appointments:
                return ToolResult.ok(
                    message="Nenhum compromisso encontrado",
                    data={"appointments": [], "count": 0},
                    display_text="📅 Você não tem compromissos agendados.",
                )

            # Format for display
            appointment_list = []
            for apt in appointments:
                apt_dict = {
                    "id": apt.id,
                    "title": apt.title,
                    "scheduled_at": apt.scheduled_at,
                    "duration_minutes": apt.duration_minutes,
                }
                appointment_list.append(apt_dict)

            # Build display text
            lines = ["📅 Seus compromissos:"]
            for i, apt in enumerate(appointment_list, 1):
                # Format datetime for display
                scheduled = apt["scheduled_at"]
                if scheduled:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
                        formatted = dt.strftime("%d/%m %H:%M")
                    except Exception:
                        formatted = scheduled
                else:
                    formatted = "?"

                lines.append(f"{i}. {apt['title']} - {formatted}")

            return ToolResult.ok(
                message=f"Encontrados {len(appointment_list)} compromissos",
                data={"appointments": appointment_list, "count": len(appointment_list)},
                display_text="\n".join(lines),
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao listar compromissos: {str(e)}")
