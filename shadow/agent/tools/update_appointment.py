"""
UpdateAppointment Tool - Updates an existing appointment.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class UpdateAppointmentTool(Tool):
    """Updates an existing appointment in the system."""

    name = "update_appointment"
    description = "Atualiza um compromisso existente (título, data/hora ou duração)"
    category = "appointments"

    parameters = [
        ToolParameter(
            name="appointment_id",
            type="integer",
            description="ID do compromisso a ser atualizado",
            required=True,
        ),
        ToolParameter(
            name="title",
            type="string",
            description="Novo título do compromisso",
            required=False,
        ),
        ToolParameter(
            name="scheduled_at",
            type="string",
            description="Nova data/hora (ISO 8601 ou texto como 'amanhã às 14h')",
            required=False,
        ),
        ToolParameter(
            name="duration_minutes",
            type="integer",
            description="Nova duração em minutos",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        appointment_id = params.get("appointment_id")
        if not appointment_id:
            return ToolResult.error("ID do compromisso é obrigatório")

        title = params.get("title")
        scheduled_at_input = params.get("scheduled_at")
        duration_minutes = params.get("duration_minutes")

        # At least one field must be provided
        if title is None and scheduled_at_input is None and duration_minutes is None:
            return ToolResult.error("Pelo menos um campo deve ser fornecido para atualização")

        # Parse scheduled_at if provided
        scheduled_at = None
        if scheduled_at_input:
            scheduled_at = self._parse_datetime(scheduled_at_input, context)

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        try:
            appointment = storage.update_appointment(
                appointment_id=appointment_id,
                title=title,
                scheduled_at=scheduled_at,
                duration_minutes=duration_minutes,
            )

            if not appointment:
                return ToolResult.error(f"Compromisso #{appointment_id} não encontrado")

            # Build update description
            updates = []
            if title:
                updates.append(f"título: {title}")
            if scheduled_at_input:
                updates.append(f"data/hora: {scheduled_at_input}")
            if duration_minutes:
                updates.append(f"duração: {duration_minutes}min")

            return ToolResult.ok(
                message="Compromisso atualizado com sucesso",
                data={
                    "appointment_id": appointment.id,
                    "title": appointment.title,
                    "scheduled_at": appointment.scheduled_at,
                    "duration_minutes": appointment.duration_minutes,
                },
                display_text=f"✅ Compromisso #{appointment_id} atualizado: {', '.join(updates)}",
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao atualizar compromisso: {str(e)}")

    def _parse_datetime(self, datetime_str: str, context: ToolContext) -> str | None:
        """Parse datetime string to ISO format using dateparser."""
        import dateparser
        from datetime import datetime

        if not datetime_str:
            return None

        parsed = dateparser.parse(
            datetime_str,
            languages=['pt', 'en'],
            settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now(),
            }
        )

        if parsed:
            return parsed.isoformat()
        return None
